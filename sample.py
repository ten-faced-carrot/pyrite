import time
from pyrite import RebalancingScheduler, Task, cooperative_sleep

def task_print():
    print("Hello World!")

def task_tiny_sleep():
    time.sleep(.01)
    print("Slept!")

def task_long_sleep():
    time.sleep(5)
    print("Deepslept")

def task_cooperative_sleep():
    print("Doing work")
    cooperative_sleep(5000)
    print("Did work.")

def task_errors():
    assert False

tasks = [
    Task(task_print, 500, name="Print"),
    Task(task_long_sleep, 500, name="Slow Task"),
    Task(task_cooperative_sleep, 500, name="Cooperative Sleep"),
    Task(task_tiny_sleep, 250, name="Short Sleep"),
    Task(task_errors, 250, name="Erroring Task"),
]

sched = RebalancingScheduler(tasks)

sched.add_service_function(lambda: time.sleep(.01))

for task in tasks:
    print(task.pid)

print("Handing off to scheduler.")
sched.run_forever()