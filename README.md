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