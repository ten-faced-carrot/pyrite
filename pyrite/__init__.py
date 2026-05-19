"""
Pyrite is a very dirty implementation of several Schedulers for Python/Micropython, mostly designed for myself.


Say you want to keep track of the following three things and ensure they all run at different intervals, without clogging up your main Loop:


```
def blink_led():
    LED.toggle()

def update_screen():
    fb.fill(0)
    fb.text(time.ticks_ms(), 0, 0)
    fb.show()

def read_temp():
    temp_reading = dht.read()

```,

then a normal approach may be to run them all in one loop. But what if you want custom delays for each? You could start keeping track of the last time a function has executed, ...


This is where Pyrite comes in. The word Pyrite is meant to take a jab at an RTOS, even though that's not what we're doing here, because as much as I'd love to, Micropython just cannot preempt tasks.

First, let's reorganize your code into Tasks. A Task only takes 2 inputs, the Function to run and the interval in milliseconds it should run at.

```
from pyrite import Task

tasks = [
    Task(blink_led, 500),
    Task(update_screen, 100),
    Task(read_temp, 5000)
]
```

And now, we can use the SimpleScheduler Class.

```
from pyrite import SimpleScheduler

sched = SimpleScheduler(tasks)
sched.run_forever()
```
This handles everything for you, with one striking issue:

What happens if a function takes very long to complete? Well sadly Micropython offers no way to "pause" Execution, so instead we use Pyrites RebalancingScheduler.

This one "punishes" a Task if it takes longer than its interval, by measuring how long it takes and skipping it for exactly that amount of time, before allowing it to run again, giving way to the other tasks.


```
# Slow-ass Task
def slow():
    time.sleep(10)
tasks.append(Task(slow, 500))

sched = RebalancingScheduler(tasks)
sched.run_forever()
```

Would run the slow task once and then skip it for Ten Seconds, or however long it took.

## Limitations

While certainly more practical than a SimpleScheduler, the RebalancingScheduler, nor anything other I can implement in Micropython cannot prevent a task from hogging up CPU Time.
Actual Fairness is pretty hard to implement. A more advanced model may punish a task that repeatedly overdraws its time, but this was a simple solution that works well enough in most cases. 
Don't worry though, I'm working on new and improved ways to make this work!

And because I didn't say it enough times already, Never never never never!! call blocking I/O or long sleep() inside tasks. That just clogs execution up for all other Tasks. No Rebalancing can ever be as good as a SimpleScheduler() whose tasks finish so quickly that there is no need to Rebalance.

"""


import time

DISPLAY_MT_WARNING = True


if hasattr(time, "ticks_ms"):
    ### MicroPython Environment
    ticks_fn = time.ticks_ms
    diff_fn = time.ticks_diff
    ticks_add = time.ticks_add
    sleep_ms = time.sleep_ms
else:
    """
    Reinventing the wheel because Micropython's Time Library is objectively better than CPythons, fight me
    """
    ticks_fn = lambda: int(time.monotonic() * 1000)
    diff_fn = lambda a, b: a - b
    ticks_add = lambda a, b: a+b
    sleep_ms = lambda m: time.sleep(m/1000)

class MissedTickPolicy:
    """
    Tells the Scheduler how to handle missed Executions.

    SKIP: Just ignore the skipped executions and continue normally
    BURST: Run the Task until it finished executing as many times as it missed
    """

    SKIP = 0
    BURST = 1

class Task:
    def __init__(self, update_fn, interval_ms, name = None, mt_policy = MissedTickPolicy.SKIP, immediate = False):
        global DISPLAY_MT_WARNING

        now = ticks_fn()
        if mt_policy == MissedTickPolicy.BURST and DISPLAY_MT_WARNING:
            DISPLAY_MT_WARNING = False

            print(
                "WARNING: BURST mode can create death spirals under heavy load. "
                "If tasks keep overrunning, the scheduler may spend all its time "
                "replaying missed executions."
            )
        self.update_fn = update_fn
        self.interval_ms = interval_ms
        self.next_run = now if immediate else ticks_add(now, interval_ms)
        self.pid = None
        self.name = name
        self.overruns = 0 # Putting this here for Future-Proofing.

        self.mt_policy = mt_policy

        self.total_runs = 0
        self.total_runtime = 0
        self.last_runtime = 0

    def run(self):
        try:
            tstart = ticks_fn()
            self.update_fn()
            self.last_runtime = diff_fn(ticks_fn(), tstart)
            self.total_runs += 1
            self.total_runtime += self.last_runtime
        except Exception as ex:
            print(f"Task {self.name} ({self.pid}) crashed - {ex}")


class SimpleScheduler:
    """
    A Simple Cooperative Scheduler that assumes each function finished super quickly.
    """
    def __init__(self, tasks: list[Task] = None):
        self.tasks = tasks or []
        self.MAX_BURST = 3
        self.servicing_functions = []
        self._next_pid = 0

    def add_service_function(self, fn):
        """
        Adds a Service Function to the Scheduler. Service Functions run after the scheduler finishes .run_once().

        This could, for example, be used to add delays between loops to give the CPU time to breathe, see the docs for the reasons.

        Note that, unlike tasks, Service Functions will NOT run in a scheduled context, so if you mess those up the whole Scheduler hangs.
        """
        self.servicing_functions.append(fn)

    def add_tasks(self, *t: list[Task]):
        for task in t:
            task.pid = self._next_pid
            self._next_pid += 1
        self.tasks.extend(t)


    def run_forever(self, iterdelay=1):
        """
        Hands all execution to the Scheduler, which runs the tasks according to its schedule.

        iterdelay: Number of milliseconds the CPU pauses before starting the loop again. Can be low or high, but should at least be lower than the shortest Task interval.
        """

        while True:
            self.run_once()
            for func in self.servicing_functions:
                func()

    def run_once(self):
        for task in self.tasks:
            now = ticks_fn()
            #print(diff_fn(ticks_fn(), task.last_execution), task.interval_ms, task.last_execution)
            if diff_fn(now, task.next_run) >= 0:
                task.run()
                
                elapsed = diff_fn(now, task.next_run)
                missed = elapsed // task.interval_ms
                missed = min(missed, self.MAX_BURST)

                for _ in range(missed):
                    if task.mt_policy == MissedTickPolicy.BURST:
                        task.run()

                task.next_run = ticks_add(task.next_run, task.interval_ms * (missed + 1))
                
class RebalancingScheduler:
    """
    A stricter reimplementation of the SimpleScheduler that detects when a Task takes longer than its tick Interval
    and then skips it until its worked down all of its overtime, so that the total time all tasks share roughly remains equal.

    Note that this scheduler, while "fairer" than the Simple one, doesn't scale well if tasks repeatedly overrun. Hold tight, I'm working on an alternative

    """
    def __init__(self, tasks = None):
        self.tasks = tasks or []
        self.loop_skip_count = {}
        self.MAX_BURST = 3
        self.servicing_functions = []
        self._next_pid = 0

    def add_service_function(self, fn):
        """
        Adds a Service Function to the Scheduler. Service Functions run after the scheduler finishes .run_once().

        This could, for example, be used to add delays between loops to give the CPU time to breathe, see the docs for the reasons.

        Note that, unlike tasks, Service Functions will NOT run in a scheduled context, so if you mess those up the whole Scheduler hangs.
        """
        self.servicing_functions.append(fn)

    def add_tasks(self, *t: list[Task]):
        for task in t:
            task.pid = self._next_pid
            self._next_pid += 1
        self.tasks.extend(t)

    def run_forever(self):
        """
        Hands all execution to the Scheduler, which runs the tasks according to its schedule.

        iterdelay: Number of milliseconds the CPU pauses before starting the loop again. Can be low or high, but should at least be lower than the shortest Task interval.
        """
        while True:
            self.run_once() 
            for function in self.servicing_functions:
                function()


    def run_once(self):
        for task in self.tasks:
            now = ticks_fn()
            if task.pid in self.loop_skip_count:
                remaining = diff_fn(self.loop_skip_count[task.pid], ticks_fn())

                if remaining > 0:
                    continue

                print(f"Task {task.pid} overtime expired")
                self.loop_skip_count.pop(task.pid)
                #print(diff_fn(ticks_fn(), task.last_execution), task.interval_ms, task.last_execution)
            if diff_fn(now, task.next_run) >= 0:
                tnow = now # Store a Pre-Execution Timestamp
                task.run()
                now = ticks_fn()
                time_took = diff_fn(now, tnow)
                if time_took > task.interval_ms:
                    print(f"{task.name} (PID {task.pid}) overran by {time_took-task.interval_ms}ms")
                    self.loop_skip_count[task.pid] = ticks_add(now, time_took - task.interval_ms)
                    task.overruns += 1


                elapsed = diff_fn(tnow, task.next_run)
                missed = elapsed // task.interval_ms
                missed = min(missed, self.MAX_BURST)

                for _ in range(missed):
                    if task.mt_policy == MissedTickPolicy.BURST:
                        task.run()

                task.next_run = ticks_add(task.next_run, task.interval_ms * (missed + 1))
                

def cooperative_sleep(ms):
    """
    TODO finish ts

    The better time.sleep_ms() as it gives the scheduler control to do stuff
    """
    end = ticks_add(ticks_fn(), ms)

    while diff_fn(end, ticks_fn()) > 0:
        sleep_ms(1)
        yield