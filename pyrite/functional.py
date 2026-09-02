"""
You know, it's weird. I think I might have Stockholm Syndrome for Scheme. Like scheme is objectively a horrendous language for actually doing things, yet I can't get away from it.

So in case you have developed the same conidition (for which I'm now coining the term "Schemeholm Syndrome" and expect everyone ever to use it) here you go enjoy my scheme inspired functional wrapper.

This is not imported by default - if you really want to use this, you have to do from pyrite.functional import <whatever>
"""

from pyrite.tasks import Task
from pyrite.compat import ticks_fn
from pyrite.states import MissedTickPolicy, ErrorPolicy

def functional(function):
    """
    Simple stub.
    """
    return Task(function, 0)

def every(interval_ms, task: Task):
    if not isinstance(task, Task): raise TypeError("Wrap your function in a functional(...) call.")
    task.interval_ms = interval_ms
    return task

def require(dependency, task: Task):
    if not isinstance(task, Task): raise TypeError("Wrap your function in a functional(...) call.")
    task.requires.append(dependency)
    return task

def after(dependency, task: Task):
    if not isinstance(task, Task): raise TypeError("Wrap your function in a functional(...) call.")
    task.after.append(dependency)
    return task


def unless(exclusion, task: Task):
    if not isinstance(task, Task): raise TypeError("Wrap your function in a functional(...) call.")
    task.unless.append(exclusion)
    return task

def oneshot(task: Task):
    if not isinstance(task, Task): raise TypeError("Wrap your function in a functional(...) call.")
    task.oneshot = True
    return task

def immediate(task: Task):
    if not isinstance(task, Task): raise TypeError("Wrap your function in a functional(...) call.")
    task.next_run = ticks_fn()
    return task

def run_immediately(task: Task):
    """For consistency with the create_task API"""
    return immediate(task)

def error_policy(policy: ErrorPolicy, task: Task):
    if not isinstance(task, Task): raise TypeError("Wrap your function in a functional(...) call.")
    if not isinstance(policy, ErrorPolicy) and not isinstance(policy, int): raise TypeError("Error Policy Must be of type ErrorPolicy")
    task.error_policy = policy
    return task
    
def missed_tick_policy(policy: MissedTickPolicy, task: Task):
    if not isinstance(task, Task): raise TypeError("Wrap your function in a functional(...) call.")
    if not isinstance(policy, MissedTickPolicy) and not isinstance(policy, int): raise TypeError("Missed Tick Policy Must be of type MissedTickPolicy")
    task.missed_tick_policy = policy
    return task
