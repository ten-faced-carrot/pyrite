"""
Pyrite is a semi-competent implementation of several Scheduling Algorithms for Python/Micropython, mostly designed because Asyncio sucks balls to use.
"""


import typing

from pyrite.logging import Logger
from pyrite.contextsys import SchedulingContext
from pyrite.tasks import Task
# NEW FOR SEPTEMBER '26! Pyrite now supports a functional API via pyrite.functional
from pyrite.compat import ticks_fn, ticks_add, diff_fn, print_exc_fn
from pyrite.states import TaskState, MissedTickPolicy, ErrorPolicy
from pyrite.watchdog import Watchdog

logger = Logger(Logger.WARN)

def configure_logger(level):
    logger.level = level

class Target: # Fuck you *installs SystemD on your esp32*
    def __init__(self, name):
        self.name = name

class Lock: # Same abstraction as Target. I don't know what abstraction means but it feels fitting.
    def __init__(self, resource):
        self.name = resource


class BasicScheduling:
    def __init__(self):
        self.crash_policy = ErrorPolicy.CRASH
     
    def run(self, task: Task, ctx: SchedulingContext):
        try:
            task.state = TaskState.PENDING
            task.run(ctx)
            task.last_run_tick = self.tick
            if task.state == TaskState.SUCCEEDED:
                for lock in ctx.locks.locked_resources:
                    if lock[0] == task.pid:
                        ctx.locks.queue_unlock(lock) # Automagically unlock held locks.
            ctx.locks.unlock_queued()
            if task.oneshot: 
                task.disabled = True
            task.backoff = 2 # If a Task runs successfully, we'll reset the Backoff - we don't want functions that might randomly crash (like I2C or flaky sensors) to be silently throttled to oblivion
            return True
        except Exception as ex:
            task.last_run_tick = self.tick
            task.state = TaskState.CRASHED
            logger.error(f"Task {task.name} (PID {task.pid}) crashed - {ex} - {print_exc_fn(ex)}")
            if task.error_policy != ErrorPolicy.INHERIT: crash_policy = task.error_policy
            else: crash_policy = self.crash_policy
            if crash_policy == ErrorPolicy.CRASH: raise ex
            elif crash_policy == ErrorPolicy.RETRY: 
                task.next_run = ticks_add(task.next_run, task.interval_ms)
            elif crash_policy == ErrorPolicy.DISABLE: task.disabled = True
            elif crash_policy == ErrorPolicy.BACKOFF: 
                now = ticks_fn()
                delay_ms = task.backoff * 1000 
                task.next_run = ticks_add(now, delay_ms)
                task.backoff = min(task.backoff * 2, 256)
                logger.warn(f"Task crashed. Backing off {task.backoff}s. Next run: {task.next_run} (In {diff_fn(task.next_run, now)})")
            for lock in ctx.locks.locked_resources:
                if lock[0] == task.pid:
                    ctx.locks.queue_unlock(lock) # Automagically unlock held locks.

            ctx.locks.unlock_queued()
            return False
        
    
class SimpleScheduling(BasicScheduling):
    """
    A Simple Cooperative Scheduler that assumes each function finished super quickly.
    """
    def __init__(self, crash_policy: int = ErrorPolicy.CRASH):
        self.max_burst = 3
        self.tick = 0
        self.crash_policy = crash_policy
        super().__init__()

    def run_once(self, tasks, ctx: SchedulingContext = None):
        self.tick += 1
        tasks_by_id = {t.name: t for t in tasks}
        for task in tasks:
            ctx.current_task_pid = task.pid
            if task.blocked_target:
                if task.blocked_target in ctx.dispatched_targets:
                    task.blocked_target = None  # Unblock!
                else:
                    # Check timeout
                    if task.blocked_timeout:
                        if diff_fn(ticks_fn(), task.blocked_start) > task.blocked_timeout:
                            task.blocked_target = None  # Timeout, unblock anyway
                    continue  # Skip this task
            dependencies_ready = True
            for dependency in task.after:
                if isinstance(dependency, Target):
                    if dependency.name not in ctx.dispatched_targets:
                        dependencies_ready = False
                elif t := tasks_by_id.get(dependency):
                    if t.last_run_tick < task.last_run_tick:
                        dependencies_ready = False
                else: raise ValueError(f"Task not found: {dependency}")
            for dependency in task.requires:

                if isinstance(dependency, Target):
                    if dependency.name not in ctx.dispatched_targets:
                        dependencies_ready = False
                elif isinstance(dependency, Lock): # I don't know why you would want to use a Lock here but I'm adding it regardless
                    if dependency.name not in map(ctx.locks.locked_resources):
                        dependencies_ready = False
                elif t := tasks_by_id.get(dependency):
                    if t.state != TaskState.SUCCEEDED:
                        dependencies_ready = False
                else: raise ValueError(f"Task not found: {dependency}")
            for dependency in task.unless:

                if isinstance(dependency, Target):
                    if dependency.name  in ctx.dispatched_targets:
                        dependencies_ready = False
                elif isinstance(dependency, Lock):
                    if dependency.name in ctx.locks.locked_resources:
                        dependencies_ready = False
                elif t := tasks_by_id.get(dependency):
                    if t.state == TaskState.SUCCEEDED:
                        dependencies_ready = False


            if task.disabled or not dependencies_ready: 
                continue

            now = ticks_fn()
            if diff_fn(now, task.next_run) >= 0:
                if self.run(task, ctx):
                
                    elapsed = diff_fn(now, task.next_run)
                    missed = (elapsed // task.interval_ms) if task.interval_ms else elapsed
                    missed = min(missed, self.max_burst)

                    for _ in range(missed):
                        if task.missed_tick_policy == MissedTickPolicy.BURST:
                            self.run(task, ctx)

                    task.next_run = ticks_add(task.next_run, task.interval_ms * (missed + 1) + task._extra_delay)
                    task._extra_delay = 0
        
class PunitiveScheduling(BasicScheduling):
    """
    A stricter reimplementation of the SimpleScheduler that detects when a Task takes longer than its tick Interval
    and then skips it until its worked down all of its overtime, so that the total time all tasks share roughly remains equal.

    Note that this scheduler, while "fairer" than the Simple one, doesn't scale well if tasks repeatedly overrun. Hold tight, I'm working on an alternative

    """
    def __init__(self, crash_policy: int = ErrorPolicy.CRASH):
        super().__init__()
        self.loop_skip_count = {}
        self.max_burst = 3      # Yes this is arbitrary womp womp pipe down
        self.max_overruns = 10  # Yes so is this, I'm adding something to do that later
        self.crash_policy = crash_policy
        self.consecutive_overrunners = {} # And yes this is not ideal either, but it's the simplest way to track consecutive overruns and should work good enough.
        self.tick = 0

    def run_once(self, tasks, ctx: SchedulingContext):
        self.tick += 1
        tasks_by_id = {t.name: t for t in tasks}
        for task in tasks:
            ctx.current_task_pid = task.pid
            dependencies_ready = True
            if task.blocked_target:
                if task.blocked_target in ctx.dispatched_targets:
                    task.blocked_target = None  # Unblock!
                else:
                    # Check timeout
                    if task.blocked_timeout:
                        if diff_fn(ticks_fn(), task.blocked_start) > task.blocked_timeout:
                            task.blocked_target = None  # Timeout, unblock anyway
                    continue  # Skip this task
            for dependency in task.after:
                
                if isinstance(dependency, Target): 
                    if dependency.name not in ctx.dispatched_targets:
                        dependencies_ready = False
                elif t := tasks_by_id.get(dependency):
                    if not t: raise ValueError(f"Task not found: {t}")
                    if t.last_run_tick < task.last_run_tick:
                        dependencies_ready = False

            for dependency in task.requires:
                
                if isinstance(dependency, Target):
                    if dependency.name not in ctx.dispatched_targets:
                        dependencies_ready = False
                elif t := tasks_by_id.get(dependency):
                    if not t: raise ValueError(f"Task not found: {t}")
                    if t.state is not TaskState.SUCCEEDED:
                        dependencies_ready = False

            for dependency in task.unless:

                if isinstance(dependency, Target):
                    if dependency.name  in ctx.dispatched_targets:
                        dependencies_ready = False
                elif t := tasks_by_id.get(dependency):
                    if t.state == TaskState.SUCCEEDED:
                        dependencies_ready = False

            if task.disabled or not dependencies_ready: 
                continue
            
            if self.consecutive_overrunners.get(task.pid, 0) > self.max_overruns:
                task.disabled = True
                self.consecutive_overrunners.pop(task.pid)
                logger.error(f"Disabled {task.name} - chronic overrunner")

            now = ticks_fn()
            if task.pid in self.loop_skip_count:
                remaining = diff_fn(self.loop_skip_count[task.pid], ticks_fn())

                if remaining > 0:
                    continue

                logger.info(f"Task {task.pid} overtime expired")
                self.loop_skip_count.pop(task.pid)
                #print(diff_fn(ticks_fn(), task.last_execution), task.interval_ms, task.last_execution)
            if diff_fn(now, task.next_run) >= 0:
                
                tnow = now # Store a Pre-Execution Timestamp
                if self.run(task, ctx):

                    now = ticks_fn()
                    time_took = diff_fn(now, tnow)
                    if time_took > task.interval_ms:
                        logger.warn(f"{task.name} (PID {task.pid}) overran by {time_took-task.interval_ms}ms (Overran {self.consecutive_overrunners.get(task.pid, 0) + 1} times)")

                        self.loop_skip_count[task.pid] = ticks_add(now, time_took - task.interval_ms)
                        task.overruns += 1
                        self.consecutive_overrunners[task.pid] = self.consecutive_overrunners.get(task.pid, 0) + 1
                        if self.consecutive_overrunners.get(task.pid, 0) > self.max_overruns / 2:
                            task.next_run = ticks_add(task.next_run, min(self.consecutive_overrunners.get(task.pid, 0) * 1000, 10000))  # Back off interval
                            logger.info(f"Reduced {task.name}'s Frequency (Next run in {diff_fn(now, task.next_run)})")
                        
                    else: 
                        self.consecutive_overrunners.pop(task.pid, 0) # Adding the 0 here because otherwise this might throw a KeyError and I can't be bothered to wrap this in Try/Except 
                        task.interval_ms = task.original_interval_ms

                    elapsed = diff_fn(tnow, task.next_run)
                    missed = (elapsed // task.interval_ms) if task.interval_ms else elapsed
                    missed = min(missed, self.max_burst)

                    for _ in range(missed):
                        if task.missed_tick_policy == MissedTickPolicy.BURST:
                            self.run(task, ctx)

                    task.next_run = ticks_add(task.next_run, task.interval_ms * (missed + 1) + task._extra_delay)
                    task._extra_delay = 0


class Scheduler:
    """
    Base Scheduler Class.
    """
    def __init__(self, algorithm = SimpleScheduling, crash_policy = ErrorPolicy.CRASH):
        self.tasks = []
        self.MAX_BURST = 3
        self.servicing_functions = []
        self.algorithm = algorithm(crash_policy)
        self._next_pid = 0
        self.task_queue = []
        self.tasks_locked = False
        self.loop_context = SchedulingContext() # Gets cleared every Loop
        self.schedule_context = SchedulingContext() # Retains State forever
        self.watchdog = Watchdog()

        self._sexvars = {}  # Registry of all SEXVars

    def register_sexvar(self, handle, sexvar):
        self._sexvars[handle] = sexvar

    def get_sexvar(self, handle):
        return self._sexvars.get(handle)

    def add_service_function(self, fn):
        """
        Adds a Service Function to the Scheduler. Service Functions run after the scheduler finishes .run_once().

        This could, for example, be used to add delays between loops to give the CPU time to breathe, see the docs for the reasons.

        Note that, unlike tasks, Service Functions will NOT run in a scheduled context, so if you mess those up the whole Scheduler hangs.
        """
        self.servicing_functions.append(fn)

    def add_task(self, t: Task):
        if t.interval_ms == 0 and not t.oneshot: raise ValueError("Tasks can't run on Zero-Tick Intervals") # We would run into a ZeroDivisionError later.
        self.add_tasks([t])

    def add_tasks(self, t: typing.Union[Task, list[Task]]):
        if self.tasks_locked: 
            self.task_queue.extend(t if isinstance(t, list) else [t])
            return
        tasks = []
        if isinstance(t, Task): t = [t]
        for task in t:
            if task.interval_ms == 0 and not task.oneshot: raise ValueError("Tasks can't run on Zero-Tick Intervals")
            task.pid = self._next_pid
            self._next_pid += 1
            tasks.append(task)
        self.tasks.extend(tasks)


    def to_mermaid(self):
        lines = ["graph TD"]
        
        for task in self.tasks:
            for dep in task.requires:
                if isinstance(dep, Target):
                    lines.append(f"  {dep.name}[{dep.name}] -->|requires| {task.name}")
                else:
                    lines.append(f"  {dep} -->|requires| {task.name}")
            
            for dep in task.unless:
                if isinstance(dep, Target):
                    lines.append(f"  {dep.name}[{dep.name}] -->|unless| {task.name}")
                else:
                    lines.append(f"  {dep} -->|unless| {task.name}")
        
        return "\n".join(lines)

    def run_forever(self, stop_after_ms = None):
        """
        Hands all execution to the Scheduler, which runs the tasks according to its schedule.

        stop_after_ms: Exits the Main Loop after :stop_after_ms: milliseconds
        """
        start_time = ticks_fn()
        if self.watchdog.alive:
            self.watchdog.start()
        while True:
            self.watchdog.heartbeat()
            self.run_once()
            if stop_after_ms:
                self.watchdog.alive = False
                if diff_fn(ticks_fn(), start_time) > stop_after_ms: return

    def set_error_policy(self, policy):
        self.algorithm.crash_policy = policy

    def set_max_bursts(self, burst: int):
        if not isinstance(burst, int): raise TypeError("MAX_BURSTS Must be an integer")
        if burst < 1: raise ValueError("MAX_BURSTS Must be >0")
        self.algorithm.max_burst = burst

    def set_max_consecutive_overruns(self, overruns: int):
        if not isinstance(overruns, int): raise TypeError("MAX_OVERRUNS Must be an integer")
        if overruns < 1: raise ValueError("MAX_OVERRUNS Must be >0")
        if not isinstance(self.algorithm, PunitiveScheduling): raise TypeError("This value can only be set for PunitiveScheduling")
        self.algorithm.max_overruns = overruns


    def run_once(self):
        self.loop_context.clear()
        try:
            self.tasks_locked = True
            self.algorithm.run_once(self.tasks, self.schedule_context)
            for func in self.servicing_functions:
                func()
        finally:
            self.tasks_locked = False
            self.add_tasks(self.task_queue)
            self.task_queue.clear()