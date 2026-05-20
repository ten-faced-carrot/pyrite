"""
Pyrite is a semi-competent implementation of several Scheduling Algorithms for Python/Micropython, mostly designed because Asyncio sucks balls to use.
Proper docs are in the docs.md File! This is more of a simple tutorial
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

First, let's reorganize your code into Tasks. At the most basic level, a Task only takes 2 inputs, the Function to run and the interval in milliseconds it should run at.

```
from pyrite import Task

tasks = [
    Task(blink_led, 500),
    Task(update_screen, 100),
    Task(read_temp, 5000)
]
```

And now, we can use the Scheduler Class, along with SimpleScheduling()

```
from pyrite import Scheduler, SimpleScheduling

sched = Scheduler(SimpleScheduling)
sched.add_tasks(tasks)
sched.run_forever()
```
This handles everything for you, with one striking issue:

What happens if a function takes very long to complete? Well sadly Micropython offers no way to "pause" Execution, so instead we use Pyrites PunitiveScheduling.

This one "punishes" a Task if it takes longer than its interval, by measuring how long it takes and skipping it for exactly that amount of time, before allowing it to run again, giving way to the other tasks.
Furthermore, chronic overrunners get punished, if a function overruns for ~PunitiveScheduling.MAX_OVERRUNS / 2 consecutive times, it gets its frequency throttled, if it overruns for ~PunitiveScheduling.MAX_OVERRUNS consecutive times, 
the scheduler disables it on the assumption that the function is broken.


```
# Slow-ass Task
def slow():
    time.sleep(10)Rebalancing
tasks.append(Task(slow, 500))

sched = Scheduler(PunitiveScheduling)
sched.add_tasks(tasks)
sched.run_forever()
```

Would run the slow task once and then skip it for Ten Seconds, or however long it took.

## Service Functions
This is probably important to talk about. By default, when using scheduler.run_forever(), there is no delay in between runs.
This is because Pyrite assumes it's the only thing running on the System and is fine hogging up 100% of the CPU. But this is bad for a Low-Power
environment. Here you can use Service Functions, which are functions that get called after the scheduler is done running the tasks.
Service Functions take no parameters. Even something as simple as

```
def idle_time():
    time.sleep_ms(1)
sched.add_service_function(idle_time)
```
Will lift a lot of stress off the CPUs shoulders.

**Important!** A Service function does not get tracked and scheduled. Pyrite assumes that Service Functions are regular and deterministic routines,
which means that there is no penalty for blocking IO, which can throw off the entire Scheduler!

## Inter-Task Communication

While definitely not fully fletched-out, Pyrite provides several Ways to communicate data between tasks. It carries data in a class called SchedulingContext().
For Future-proofing reasons, let it be known that task functions can use this class to read metadata about their Task as well.

A Context fundamentally provides two ways of communication.
One of them is a Message Queue and the other one is called "flags" and is essentially just a big dictionary accessible to everyone.

Contexts are exposed through the Scheduler, which has two Objects. One named "loop_context", which clears every Scheduling Loop and one named "schedule_context"
which retains its state until manually .clear()ed.

So a simple use of this might be:
```
def sensor_task():
    temp = dht.read()
    scheduler.schedule_context.push_msg({"sensor": temp})

def display_task():
    while scheduler.schedule_context.message_queue:
        msg = scheduler.schedule_context.pop_msg()
        fb.text(str(msg["sensor"]), 0, 0)
        fb.show()
```

Mailbox-Driven Designs are in the works, but I'm not sure if that is really neccessary

## Limitations

While certainly more practical than a SimpleScheduler, the PunitiveScheduler, nor anything other I can implement in Micropython cannot prevent a task from hogging up CPU Time.
Actual Fairness is pretty hard to implement. A more advanced model may punish a task that repeatedly overdraws its time, but this was a simple solution that works well enough in most cases. 
Don't worry though, I'm working on new and improved ways to make this work!
And because I didn't say it enough times already, Never never never never!! call blocking I/O or long sleep() inside tasks. 
Stress Tests I made show that the PunitiveScheduling System still manages to keep the Ratios of all Tasks fair, but still sleeping just steals other tasks' Runtimes.
That just clogs execution up for all other Tasks. No Rebalancing can ever be as good as a SimpleScheduler() whose tasks finish so quickly that there is no need to Rebalance.

Furthermore, Pyrite *as of now* operates on the principle that the user writes working code. Pyrite provides basic Error Handling (See the docs.md file), but Errors can still render your code in an unknown state, hence why Pyrite's Default Error Behavior is to crash so you can cleanly restart.

"""


import time
import typing
import sys

from pyrite.logging import Logger
from pyrite.contextsys import SchedulingContext

if hasattr(sys, "print_exception"):
    print_exc_fn = sys.print_exception
else:
    import traceback
    print_exc_fn = traceback.print_exception

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

class ErrorPolicy:
    """
    Tells the Scheduler how to handle crashed Tasks. Can either be supplied as an argument to the Scheduler or to a task. The Scheduler prefers the Tasks choice over its own.
    CRASH   : The scheduler crashes, resetting the board to a clean state. This is the default when creating a Scheduler.
    DISABLE : Disables the Erroring Task
    RETRY   : The Scheduler will attempt to run the Task in the next cycle
    BACKOFF : The Scheduler runs a crashing function less and wait between two consecutive attempts. To avoid any kind of memory overflow, this caps out at 256s.
    INHERIT : ONLY to be used inside a Task Object, tells the Scheduler that the Task has no specific Preference on how to handle Errors and will comply with the scheduler's preference.
    """
    CRASH = -1
    DISABLE = 0
    RETRY = 1
    BACKOFF = 2
    INHERIT = 3

DISPLAY_MT_WARNING = True
logger = Logger(Logger.WARN)

def configure_logger(level):
    logger.level = level

class Task:
    def __init__(self, update_fn, interval_ms, name = None, missed_tick_policy = MissedTickPolicy.SKIP, error_policy = ErrorPolicy.INHERIT, immediate = False):
        global DISPLAY_MT_WARNING

        now = ticks_fn()
        if missed_tick_policy == MissedTickPolicy.BURST and DISPLAY_MT_WARNING:
            DISPLAY_MT_WARNING = False

            logger.warn(
                "WARNING: BURST mode can create death spirals under heavy load. "
                "If tasks keep overrunning, the scheduler may spend all its time "
                "replaying missed executions."
            )
        self.update_fn = update_fn
        self.interval_ms = interval_ms
        self.error_policy = error_policy
        self.next_run = now if immediate else ticks_add(now, interval_ms)
        self.pid = None
        self.name = name or update_fn.__name__
        self.overruns = 0 # Putting this here for Future-Proofing.
        self.backoff = 2
        self.disabled = False
        self.missed_tick_policy = missed_tick_policy

        self.total_runs = 0
        self.total_runtime = 0
        self.last_runtime = 0

        self._gen = None
        self._extra_delay = 0

    def stats(self):
        """
        Returns (Task Interval in Milliseconds, Task Name, Task PID, Tasks total runs, Tasks total Runtime, Tasks last Runtime, Tast backoff timer, Task disabled)
        """
        return (self.interval_ms, self.name, self.pid, self.total_runs, self.total_runtime, self.last_runtime, self.backoff, self.disabled)

    def run(self):
        tstart = ticks_fn()
        
        if self._gen is None:
            result = self.update_fn()
            # If it returned a generator, adopt it; otherwise treat as normal fn
            if hasattr(result, '__next__'):
                self._gen = result
            else:
                self._extra_delay = 0
                self.last_runtime = diff_fn(ticks_fn(), tstart)
                self.total_runs += 1
                self.total_runtime += self.last_runtime
                return

        # Advance the generator one step
        if self._gen is not None:
            try:
                val = next(self._gen)
                self._extra_delay = (val - self.interval_ms) if isinstance(val, int) else 0
            except StopIteration:
                self._gen = None
                self._extra_delay = 0


        self.last_runtime = diff_fn(ticks_fn(), tstart)
        self.total_runs += 1
        self.total_runtime += self.last_runtime

class BasicScheduling:
    def __init__(self):
        self.crash_policy = ErrorPolicy.CRASH
     
    def run(self, task):
        try:
            task.run()
            task.backoff = 2
            return True
        except Exception as ex:
            logger.error(f"Task {task.name} (PID {task.pid}) crashed - {ex} - {print_exc_fn(ex)}")
            if task.error_policy != ErrorPolicy.INHERIT: crash_policy = task.error_policy
            else: crash_policy = self.crash_policy
            if crash_policy == ErrorPolicy.CRASH: raise ex
            elif crash_policy == ErrorPolicy.RETRY: 
                task.next_run = ticks_add(task.next_run, task.interval_ms)
            elif crash_policy == ErrorPolicy.DISABLE: task.disabled = True
            elif crash_policy == ErrorPolicy.BACKOFF: 
                now = ticks_fn()
                delay_ms = task.backoff * 1000 
                task.next_run = ticks_add(now, delay_ms)
                task.backoff = min(task.backoff * 2, 256)
                logger.warn(f"Task crashed. Backing off {task.backoff}s. Next run: {task.next_run} (In {diff_fn(task.next_run, now)})")
            return False
    

class SimpleScheduling(BasicScheduling):
    """
    A Simple Cooperative Scheduler that assumes each function finished super quickly.
    """
    def __init__(self, crash_policy: int = ErrorPolicy.CRASH):
        self.MAX_BURST = 3
        super().__init__()

    def run_once(self, tasks):
        for task in tasks:
            if task.disabled: continue

            now = ticks_fn()
            if diff_fn(now, task.next_run) >= 0:
                if self.run(task):
                
                    elapsed = diff_fn(now, task.next_run)
                    missed = elapsed // task.interval_ms
                    missed = min(missed, self.MAX_BURST)

                    for _ in range(missed):
                        if task.missed_tick_policy == MissedTickPolicy.BURST:
                            self.run(task)

                    task.next_run = ticks_add(task.next_run, task.interval_ms * (missed + 1) + task._extra_delay)
                    task._extra_delay = 0
               
class PunitiveScheduling(BasicScheduling):
    """
    A stricter reimplementation of the SimpleScheduler that detects when a Task takes longer than its tick Interval
    and then skips it until its worked down all of its overtime, so that the total time all tasks share roughly remains equal.

    Note that this scheduler, while "fairer" than the Simple one, doesn't scale well if tasks repeatedly overrun. Hold tight, I'm working on an alternative

    """
    def __init__(self, crash_policy: int = ErrorPolicy.CRASH):
        super().__init__(crash_policy)
        self.loop_skip_count = {}
        self.MAX_BURST = 3      # Yes this is arbitrary womp womp pipe down
        self.MAX_OVERRUNS = 10  # Yes so is this, I'm adding something to do that later
        
        self.consecutive_overrunners = {} # And yes this is not ideal either, but it's the simplest way to track consecutive overruns and should work good enough.

    def run_once(self, tasks):
        for task in tasks:
            if task.disabled: 
                continue
            if self.consecutive_overrunners.get(task.pid, 0) > self.MAX_OVERRUNS:
                task.disabled = True
                logger.error(f"Disabled {task.name} - chronic overrunner")

            if self.consecutive_overrunners.get(task.pid, 0) > self.MAX_OVERRUNS / 2:
                task.interval_ms = min(task.interval_ms * 2, 5000)  # Back off interval
                logger.info(f"Reduced {task.name}'s Frequency (Now {task.interval_ms}ms)")
            now = ticks_fn()
            if task.pid in self.loop_skip_count:
                remaining = diff_fn(self.loop_skip_count[task.pid], ticks_fn())

                if remaining > 0:
                    continue

                logger.info(f"Task {task.pid} overtime expired")
                self.loop_skip_count.pop(task.pid)
                #print(diff_fn(ticks_fn(), task.last_execution), task.interval_ms, task.last_execution)
            if diff_fn(now, task.next_run) >= 0:
                tnow = now # Store a Pre-Execution Timestamp
                if self.run(task):

                    now = ticks_fn()
                    time_took = diff_fn(now, tnow)
                    if time_took > task.interval_ms:
                        logger.info(f"{task.name} (PID {task.pid}) overran by {time_took-task.interval_ms}ms")
                        self.loop_skip_count[task.pid] = ticks_add(now, time_took - task.interval_ms)
                        task.overruns += 1
                        self.consecutive_overrunners[task.pid] = self.consecutive_overrunners.get(task.pid, 0) + 1
                    else: 
                        self.consecutive_overrunners.pop(task.pid, 0) # Adding the 0 here because otherwise this might throw a KeyError and I can't be bothered to wrap this in Try/Except 

                    elapsed = diff_fn(tnow, task.next_run)
                    missed = elapsed // task.interval_ms
                    missed = min(missed, self.MAX_BURST)

                    for _ in range(missed):
                        if task.missed_tick_policy == MissedTickPolicy.BURST:
                            self.run(task)

                    task.next_run = ticks_add(task.next_run, task.interval_ms * (missed + 1) + task._extra_delay)
                    task._extra_delay = 0
                

class Scheduler:
    """
    Base Scheduler Class.
    """
    def __init__(self, algorithm = SimpleScheduling, crash_policy = ErrorPolicy.CRASH):
        self.tasks = []
        self.MAX_BURST = 3
        self.servicing_functions = []
        self.algorithm = algorithm(crash_policy)
        self._next_pid = 0
        self.task_queue = []
        self.tasks_locked = False

        self.loop_context = SchedulingContext() # Gets cleared every Loop
        self.schedule_context = SchedulingContext() # Retains State forever


    def add_service_function(self, fn):
        """
        Adds a Service Function to the Scheduler. Service Functions run after the scheduler finishes .run_once().

        This could, for example, be used to add delays between loops to give the CPU time to breathe, see the docs for the reasons.

        Note that, unlike tasks, Service Functions will NOT run in a scheduled context, so if you mess those up the whole Scheduler hangs.
        """
        self.servicing_functions.append(fn)

    def add_tasks(self, t: typing.Union[Task, list[Task]]):
        if self.tasks_locked: 
            self.task_queue.extend(t if isinstance(t, list) else [t])
            return
        tasks = []
        if isinstance(t, Task): t = [t]
        for task in t:
            task.pid = self._next_pid
            self._next_pid += 1
            tasks.append(task)
        self.tasks.extend(tasks)


    def run_forever(self):
        """
        Hands all execution to the Scheduler, which runs the tasks according to its schedule.

        iterdelay: Number of milliseconds the CPU pauses before starting the loop again. Can be low or high, but should at least be lower than the shortest Task interval.
        """

        while True:
            self.run_once()
            

    def run_once(self):
        self.loop_context.clear()
        try:
            self.tasks_locked = True
            self.algorithm.run_once(self.tasks)
            for func in self.servicing_functions:
                func()
        finally:
            self.tasks_locked = False
            self.add_tasks(self.task_queue)
            self.task_queue.clear()