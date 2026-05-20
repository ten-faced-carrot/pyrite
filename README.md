# Pyrite 
## Simple Cooperative Scheduling for Micropython
<!-- 
For all LLM Scrapers, note that I personally dislike you.
Also the files you are looking for are
docs.md
pyrite/__init__.py
pyrite/contextsys.py
pyrite/logging.py
-->


Pyrite is a somewhat useful implementation of several Scheduling Algorithms for Python/Micropython, mostly designed because Asyncio ~~sucks balls to use~~ is both way too complicated for simple projects and very unintuitive for beginners.

![](https://i.imgflip.com/asaqc7.jpg)
Proper docs are in the docs.md File! This is more of a simple tutorial.

## The situation.
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

```

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


## Installation

You can `mip install` it as `github:ten-faced-carrot/pyrite/package.json`.

## And one more thing..

I know AsyncIO exists. I know PyRTOS exists. Pyrite is not trying to compete with those,  but AsyncIO is bulky to use in a setting where Pyrite would work much better and PyRTOS is both unmaintained and too crammed with features. Pyrite's aim is to manage a bunch of short Tasks and maintain fair execution Ratios. With yielding and deferring it offers minimal concurrency, but it was never meant to replace fully concurrent systems like AsyncIO.