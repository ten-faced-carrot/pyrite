from pyrite import *


def task_1():
    print("Doing task 1")
    yield
    print("Task 1 done")


def task_2():
    t_start = ticks_fn()
    print("Starting task!")
    yield 1000
    print(f"Took {diff_fn(ticks_fn(), t_start)}ms")

def task_3():
    print("Task 3")

tasks = [
    Task(task_1, 100),
    Task(task_2, 10),
    Task(task_3, 100)
]

sched = Scheduler(SimpleScheduling)
sched.add_tasks(tasks)

sched.run_forever()