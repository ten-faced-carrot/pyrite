from pyrite import *


def task_1():
    print("Task 1 done")


def task_2():
    t_start = ticks_fn()
    print("Starting task!")
    yield 1000
    print(f"Took {diff_fn(ticks_fn(), t_start)}ms")


tasks = [
    Task(task_1, 100),
    Task(task_2, 10)
]

sched = Scheduler(SimpleScheduling)
sched.add_tasks(tasks)

sched.run_forever()