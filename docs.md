# Pyrite 
## Simple Cooperative Scheduling for Micropython
Pyrite was designed to provide an alternative to uAsyncIO on Micropython (even though it works just as well on Python - Yet I personally wouldn't recommend it, as CPython has great multiprocessing support, even though the GIL is a pain).

## Basic Usage
Pyrite separates functionality into Tasks. A Task for the user is basically just a function that gets called repeatedly by the Scheduler.

A Basic pyrite project defines a Scheduler and its task functions, wraps those in `Task` objects and registers them with the `add_task` function. Once the Scheduler has been informed, you hand off functionality to the Scheduler using the `.run_forever()` function

## Tasks

A Task is an Object that contains a function which itself contains the actual code.
It accepts the following arguments:
- `update_fn`: The actual Function code.
- `interval_ms`: The interval at which the task executes, in Milliseconds.
- `name`: The Task name, defaults to the Function's `__name__`
- `missed_tick_policy`: A Flag indicating how to handle missed ticks. Defaults to SKIP, see later execution. I recommend to leave this unchanged.
- `error_policy`: A Flag indicating how to handle Function Errors. See [Error Handling](#error-handling). Defaults to ErrorPolicy.CRASH
- `immediate`: A Boolean indicating whether the Task will run immediately in the first scheduling loop
- `oneshot`: A Boolean (Default False). If set to true, the task will disable after successful execution.
- `after`: A List of Tasks (By name) or Targets (see below) that have to run before this function - Literally waits until all those functions have executed, even if they crash.
- `requires`: A List of Tasks (By name) or Targets (see below) that have to run successfully before this function - The Task will execute if and only if all those tasks have succeeded in executing
- `unless`: A List of Tasks (By name) or Targets (see below) that must NOT have completed for this task to run. Potentially useful for connecting to networks or calibrating sensors.

Preemption is nonexistent in Pyrite. The Schedulers rely on the Tasks not blocking too much, so using `.sleep()` is horrible, uncapped while loops can throw the scheduler off terribly, basically just write good code!

(Good code here means: Blocking operations (long loops, time.sleep, large computations) will break the scheduler. Try to either keep each task as short as possible, or use the waiting mechanism explained in the next section)

### Targets
A *Target* provides a publish-subscribe synchronization mechanism for coordinating tasks. They allow Tasks to signal events, wait for conditions and establish dependencies without hard-coding relationships.

A `Target` is a named signal that can be:
- Dispatched (published) by tasks
- Waited on by Tasks (yielding back control until dispatched)
- Dependency (used in `after` `requires` or `unless`)
```py
from pyrite import Target, WaitForTarget

# Create a target
data_ready = Target("data_ready")

# Use it in dependencies
task = Task(
    process_data,
    interval_ms=100,
    requires=[data_ready]  # Won't run until data_ready is dispatched
)


# Dispatching a Target
@Task.with_context
def producer_task(ctx):
    # ... produce some data ...
    ctx.dispatch_target("data_ready")  # Signal that data is available
    print("Target 'data_ready' dispatched!")

# Waiting for a target
def consumer_task():
    # Wait for data_ready target (with 5 second timeout)
    yield WaitForTarget("data_ready", timeout_ms=5000)
    
    # This code runs after the target is dispatched
    print("Data is ready, processing...")
```
- Targets are *persistent*. They will NOT reset, and act more as checkpoints.

### Locks
Locks are temporary restrictions you can use to block resources/tasks.

```py
@Task.with_context
def task_1(ctx):
    with ctx.locks.lock("name here"):
        yield 1000
```
or

```py
@Task.with_context
def task_1(ctx):
    ctx.locks.lock("name here")
    yield 1000
    ctx.locks.unlock("name here")
``` 
for a more controlled approach.

```py
def task_2(): print("Test")

tasks = [
    Task(task_1, interval_ms=1000),
    Task(task_2, interval_ms = 100, unless=[Lock("name here")])
]

```

Locks will automatically be unlocked after the function is done, or crashed.

### Waiting

Sometimes, a Waiting function is necessary.  Instead of using `time.sleep()`, Pyrite allows functions to `yield` control back to the scheduler, allowing functions to wait without locking up the whole scheduler.

```py
def task_that_waits():
    print("Doing work!")
    yield 1000 # Will delay for one second
    print("Did work!")
```

### Wait, what does this imply?
##### Pun intended
Pyrite's philosophy are short, stateless Tasks. When your task is just
```py
def task():
    adc = read_adc()
    print(adc)
```
There's no hidden leaks, it's clean and easy to debug. However it introduces a nasty reality for Tasks that *do* need a state. You'll have to use globals, or the loop_context, but neither of those are safe to use, and globals should also be avoided in general.

When I started this project, I would've just told you that there's no clean way to use stateful tasks. However, with the yield functionality, even though it doesn't match Pyrite's design philosophy, this is 100% acceptable code:

```py
def stateful_task():
    state = None
    while True:
        state = do_work()
        yield 0 # The 0 here is optional, but since default behaviour with no return results might change in later versions, you should always use it, even if you intend to sleep for 0ms.
```
or even

```py
def stateful_task():
    while True:
        yield from do_work() # Hands control over to do_work()
```
and this works, the Scheduler can keep up with that and you maintain your state in a safe way.
### The stalling system
Pyrite provides `yield <milliseconds>` to yield control, as well as WaitForTarget("targetname"). However, until now, there was no way to wait until an arbitrary condition becomes true. That changes with the new stall() operation.
```py
def task():
    yield from stall(
        until=lambda: sensor.is_ready(), # Predicate that is checked
        timeout=0, # Time stall() waits until timing out the operation, raising a TimeoutError. Setting this to 0 will disable timeouts.
        probe_interval = 100 # The time stall() waits between probes to save CPU Time.
    )

```


### The Loop Context
...is probably worth mentioning.
Because with the addition of stateful tasks, this is much less useful now.
`@Task.with_context` only passes the schedule_context, which is persistent across cycles. If you need the loop_context, you must access it through the scheduler's `loop_context` attribute. Which isn't that intuitive, admittedly.

## Context
At this point, scheduling_context is becoming so big that it probably deserves a shoutout. It's automagically passed to all functions that get declared as `@Task.with_context`. It is the most comprehensive all-in-one solution to interfacing with the Scheduler. It has the following features:

### Target Control
The SchedulingContext is what allows you to dispatch targets, which is done via the `ctx.dispatch_target("target_name")` method
### Locking
`ctx.locks` provides a way to manage locks, see the [Locks](#locks) documentation

### Inter-Task Communication
The Context provides a primitive ITC Subsystem, via a "Message Queue" as well as "Flags".

#### Messages
The Message queue is a shared double-ended queue of maximum length 5. You can interface with the following methods:
* `ctx.push_msg(payload)` pushes a payload to the Queue
* `ctx.pop_msg()` removes the first element of the Queue and returns it to the task
* `ctx.peek_msg()` returns the first element of the Queue to the task without removing it

#### Flags
Flags act as a shared dictionary between tasks:
* `ctx.set_flag(name, value=True)` sets a flag.
* `ctx.get_flag(name)` gets the content of the specified Flag, or `None` by default.
* `ctx.is_flag_set(name)` returns a boolean that determines whether that flag exists
* `ctx.clear_flag(name)` Clears that flag from the context

#### Other Metadata
`ctx.current_task_pid` returns the PID of the currently active task.


## Task builder
For ease-of-use Pyrite has adopted an easier way of creating Tasks via the create_task() call. Instead of having to specify all parameters at creation, you can now run
```py
task = create_task(funct).every(100).require(cond_a).run_after(...).require(cond_b).run_unless(exclusion).run_immediately().run_once()
```
And use that task as normal!

## Functional-Style declarations
For functional programmers, pyrite supports a Functional-Inspired Task creation process.

To start, add `from pyrite.functional import <everythign you need>`

You must then wrap your functions in a functional call, like `task = functional(my_function)`
From here, you can
```py
task = every(100, 
    requires("cond_a", 
        requires("cond_b", 
            immediate(unless("excl_a", 
                after("cond_c", functional(my_function))
            ))
        )
    )
)
``` 
and then use the task object as a normal Task.


## Schedulers

So a Scheduler is the central piece of Pyrite. There is one Scheduler Class that, as a parameter, takes in a Scheduling Algorithm, so

```
sched = Scheduler(SimpleScheduling)
```

Pyrite has several ways to Schedule Tasks. The easiest (and fastest) one is called `SimpleScheduling`, which is a primitive round-robin system. This has the advantage of being predictable, easy to understand and having practically no overhead, however it's prone to being thrown off by misbehaving Tasks. Use this for when you know that Tasks will not overrun.

The other, more complex System is called `PunitiveScheduling`. Fundamentally it still round-robins through tasks, but importantly detects when tasks terribly overrun and punishes them in the following way:
- Each time a Task overruns, its next runtime is pushed back by the amount of time it overran
- After `PunitiveScheduling.max_overruns / 2` consecutive overruns, the Task gets its executions reduced by half, or at most to 10000ms
- After `PunitiveScheduling.max_overruns` consecutive overruns, the Scheduler disables the task.
This helps ensure that all functions get a fair slice of time, although it still doesn't prevent the tasks from overrunning. Again, Pyrite just cannot preempt tasks, that's not possible in (Micro)python.

## Error Handling.
Preferably, your code doesn't have any Errors. Errors are tricky, because they can leave your Code running in an unknown State. Pyrite is aware of this and has several ways to Handle Errors.

Error Handling occurs on two levels, on the `Task` level and on the `Scheduler` Level. Each Task can define its own Crash Policy, although by default they adopt the Scheduler's policy, unless explicitly overridden. 

The Error Policies are defined in `Pyrite.ErrorPolicy`:
- `ErrorPolicy.CRASH`: Default for the Scheduler, crashes ungracefully so the board can reset to a clean state
- `ErrorPolicy.DISABLE`: Disables the Task when it crashes  
- `ErrorPolicy.RETRY`: Tries to run the Code again in the next cycle
- `ErrorPolicy.BACKOFF`: Pushes back the task for an exponentially incrementing amount of time (Capped at 256s)
- `ErrorPolicy.INHERIT`: Default behaviour for Tasks, means that the Task just adopts the Schedulers Policy.

You can either specify this on the Task level:
```py
task = Task(my_code, 100, error_policy = ErrorPolicy.BACKOFF)
```
Or on Scheduler Level.
```py
sched = Scheduler(SimpleScheduling, ErrorPolicy.BACKOFF)
```

## The Watchdog
On systems that offer the _thread library, you can enable Pyrite's Watchdog.
`scheduler.watchdog.enable()`
the Scheduler pings the Watchdog every cycle, and if the watchdog receives no heartbeat in 20 seconds it will consider the scheduler locked beyond repair and reset the board if the machine library is available, or raise a SystemError otherwise. On Systems that don't have _thread, you simply cannot use a Watchdog. This might not sound good, but it's arguably better than faking a watchdog that isn't able to do anything.