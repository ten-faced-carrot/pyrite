"""
EXPERIMENTAL CODE! Pushing for transparency and because I'm pretty sure it works, but use with caution. For now.
"""

from pyrite.schedulers import Scheduler


def secure_exchange_var(handle, initial_value, scheduler: Scheduler, read: list = [], write: list = []):
    held_value = [initial_value]
    current_scheduler = scheduler
    read_perms = read
    write_perms = write
    if current_scheduler.schedule_context.current_task_pid != None:
        raise RuntimeError("Cannot create SecureExchangeVariables at run-time, you must declare them before starting the scheduler.") # Otherwise tasks could just pollute the everliving hell out of the scheduler with sexvars

    class SEXVar: # SEXVar is short for SecureExchange Variable and nothing else, go to horny jail.
        def __init__(self):
            self.handle = handle

        @property
        def _tasks_by_pid(self):

            return {t.pid: t.name for t in current_scheduler.tasks}
        
        @property
        def value(self):
            if self._tasks_by_pid.get(current_scheduler.schedule_context.current_task_pid, "") not in read_perms and read_perms:
                raise PermissionError(f"Task {current_scheduler.schedule_context.current_task_pid} tried to access Variable {self.handle} but lacks READ Permission!")
            return held_value[0]


        @value.setter
        def value(self, new_value):
            if self._tasks_by_pid.get(current_scheduler.schedule_context.current_task_pid, "") not in write_perms and write_perms:
                raise PermissionError(f"Task {current_scheduler.schedule_context.current_task_pid} tried to modify Variable {self.handle} but lacks WRITE Permission!")
            held_value[0] = new_value
            return True

    variable = SEXVar()
    current_scheduler.register_sexvar(handle, variable)
    return variable