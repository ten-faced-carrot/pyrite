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
It still doesn't solve the issue of a blocking task, but it helps prevent chronically slow tasks from permanently dominating schedule time after they complete.

```
# Slow-ass Task
def slow():
    time.sleep(10)
tasks.append(Task(slow, 500))

sched = RebalancingScheduler(tasks)
sched.run_forever()
```

Would run the slow task once and then skip it for Ten Seconds, or however long it took.
"""


import time
import random

__counter = 0

def iota(rst=False):
    global __counter
    __counter = ((not rst) * __counter) + 1
    return __counter

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
    diff_fn = lambda m, n: m - n
    ticks_add = lambda m, n: m+n
    sleep_ms = lambda m: time.sleep(m/1000)

class MissedTickPolicy:
    """
    Tells the Scheduler how to handle missed Executions.

    SKIP: Just ignore the skipped executions and continue normally
    CATCH_UP: Run the Task until it finished executing as many times as it missed
    """

    SKIP = 0
    CATCH_UP = 1


class Task:
    def __init__(self, update_fn, interval_ms, name = None, mt_policy = MissedTickPolicy.SKIP, immediate = False):
        self.update_fn = update_fn
        self.interval_ms = interval_ms
        self.last_execution = 0 if immediate else ticks_fn()
        self.pid = iota()
        self.name = name

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

    def add_task(self, t: Task):
        self.tasks.append(t)

    def run_forever(self, iterdelay=1):
        """
        Hands all execution to the Scheduler, which runs the tasks according to its schedule.

        iterdelay: Number of milliseconds the CPU pauses before starting the loop again. Can be low or high, but should at least be lower than the shortest Task interval.
        """
        while True:
            self.run_once()
            sleep_ms(int(iterdelay))

    def run_once(self):
        for task in self.tasks:
            now = ticks_fn()
            #print(diff_fn(ticks_fn(), task.last_execution), task.interval_ms, task.last_execution)
            if diff_fn(now, task.last_execution) > task.interval_ms:
                task.run()
                
                
                while diff_fn(ticks_fn(), task.last_execution) >= task.interval_ms:
                    # Missed-Tick Correction
                    if task.mt_policy == MissedTickPolicy.CATCH_UP:
                        task.run()
                    task.last_execution = ticks_add(task.last_execution, task.interval_ms)


class RebalancingScheduler:
    """
    A stricter reimplementation of the SimpleScheduler that detects when a Task takes longer than its tick Interval
    and then skips it until its worked down all of its overtime, so that the total time all tasks share roughly remains equal.

    Note that this scheduler, while "fairer" than the Simple one, doesn't scale well if tasks repeatedly overrun. Hold tight, I'm working on an alternative

    """
    def __init__(self, tasks = None):
        self.tasks = tasks or []
        self.loop_skip_count = {}

    def add_task(self, t: Task):
        self.tasks.append(t)

    def run_forever(self, iterdelay=1):
        """
        Hands all execution to the Scheduler, which runs the tasks according to its schedule.

        iterdelay: Number of milliseconds the CPU pauses before starting the loop again. Can be low or high, but should at least be lower than the shortest Task interval.
        """
        while True:
            self.run_once()
            sleep_ms(int(iterdelay))


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
            if diff_fn(now, task.last_execution) > task.interval_ms:
                tnow = now
                task.run()
                now = ticks_fn()
                time_took = diff_fn(now, tnow)
                if time_took > task.interval_ms:
                    self.loop_skip_count[task.pid] = ticks_add(now, time_took - task.interval_ms)
                while diff_fn(now, task.last_execution) >= task.interval_ms:
                    # Missed-Tick Correction
                    now = ticks_fn()
                    if task.mt_policy == MissedTickPolicy.CATCH_UP:
                        task.run()
                    task.last_execution = ticks_add(task.last_execution, task.interval_ms)