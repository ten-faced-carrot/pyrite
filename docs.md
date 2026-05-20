# Pyrite 
## Simple Cooperative Scheduling for Micropython



## Basic Usage
Pyrite seperates functionality into Tasks. A Task for the user is basically just a function that gets called repeatedly by the Scheduler.

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

Preemption is nonexistent in Pyrite. The Schedulers rely on the Tasks not blocking too much, so using `.sleep()` is horrible, uncapped while loops can throw the scheduler off terribly, basically just write good code!

### Waiting

Sometimes, a Waiting function is necessary.  Instead of using `time.sleep()`, Pyrite allows functions to `yield` control.

```py
def task_that_waits():
    print("Doing work!")
    yield 1000 # Will delay for one second
    print("Did work!")
```

## Schedulers

So a Scheduler is the central piece of Pyrite. There is one Scheduler Class that, as a parameter, takes in a Scheduling Algorithm, so

```
sched = Scheduler(SimpleScheduling)
```

Pyrite has several ways to Schedule Tasks. The easiest (and fastest) one is called `SimpleScheduling`, which is a primitive round-robin system. This has the advantage of being predictable, easy to understand and having practically no overhead, however it's prone to being thrown off by misbehaving Tasks. Use this for when you know that Tasks will not overrun.

The other, more complex System is called `PunitiveScheduling`. Fundamentally it still round-robins through tasks, but importantly detects when tasks terribly overrun and punishes them in the following way:
- Each time a Task overruns, its next runtime is pushed back by the amount of time it overran
- After `PunitiveScheduling.MAX_OVERRUNS / 2` consecutive overruns, the Task gets its executions reduced by half, or at most to 5000ms
- After `PunitiveScheduling.MAX_OVERRUNS` consecutive overruns, the Scheduler disables the task.
This helps ensure that all functions get a fair slice of time, although it still doesn't prevent the tasks from overrunning. Again, Pyrite just cannot preempt tasks, that's not possible in (Micro)python.

## Error Handling.
Preferably, your code doesn't have any Errors. Errors are tricky, because they can leave your Code running in an unknown State. Pyrite is aware of this and has several ways to Handle Errors.

Error Handling occurs on two levels, on the `Task` leven and on the `Scheduler` Level. Each Tast can define its own Crash Policy, although by default they adopt the Scheduler's policy, unless explicitly overridden. 

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