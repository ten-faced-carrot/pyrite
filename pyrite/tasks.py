from pyrite.states import TaskState, MissedTickPolicy, ErrorPolicy
from pyrite.compat import ticks_add, ticks_fn, diff_fn
from pyrite.logging import Logger
from pyrite.contextsys import _ContextFn

logger = Logger(Logger.WARN) # task objects never have to do more than WARN anyways. Figuring out a clean way anyways.
DISPLAY_MT_WARNING = True



class Task:
    def __init__(self, update_fn, interval_ms, name = None, missed_tick_policy = MissedTickPolicy.SKIP, error_policy = ErrorPolicy.INHERIT, immediate = False, oneshot = False, after=None, requires=None, unless=None):
        global DISPLAY_MT_WARNING # oops, all globals.

        now = ticks_fn()
        if missed_tick_policy == MissedTickPolicy.BURST and DISPLAY_MT_WARNING:
            DISPLAY_MT_WARNING = False

            logger.warn(
                "WARNING: BURST mode can create death spirals under heavy load. "
                "If tasks keep overrunning, the scheduler may spend all its time "
                "replaying missed executions."
            )
        self.update_fn = update_fn
        self.interval_ms = interval_ms
        self.original_interval_ms = interval_ms # So throttled tasks can reset
        self.error_policy = error_policy
        self.next_run = now if immediate else ticks_add(now, interval_ms)
        self.pid = None
        self.name = name or update_fn.__name__
        self.overruns = 0 # Putting this here for Future-Proofing.
        self.backoff = 2
        self.disabled = False
        self.missed_tick_policy = missed_tick_policy
        self.oneshot = oneshot
        self.state = TaskState.NOT_READY

        self.after = after if after else []           # Soft Dependency - Runs if all tasks in this list have at least executed once - even if they crashed
        self.requires = requires if requires else []  # Hard Dependency - Runs if and only if all tasks have succeeded
        self.unless = unless if unless else []        # Hard Dependency - Runs if and only if nothing here happens


        self.blocked_target = None
        self.blocked_timeout = 0
        self.blocked_start = 0

        self.total_runs = 0
        self.total_runtime = 0
        self.last_runtime = 0
        self.last_run_tick = 0

        self._gen = None
        self._extra_delay = 0
        self._wants_context = isinstance(self.update_fn, _ContextFn)
    def stats(self):
        """
        Returns (Task Interval in Milliseconds, Task Name, Task PID, Tasks total runs, Tasks total Runtime, Tasks last Runtime, Tast backoff timer, Task disabled)
        """
        return (self.interval_ms, self.name, self.pid, self.total_runs, self.total_runtime, self.last_runtime, self.backoff, self.disabled)

    @staticmethod
    def with_context(fn):
        """
        If added as a decorator, will pass the Scheduler's Context as a keyword argument, as `ctx`

        ```py
        @Task.with_context
        def contexttask(ctx):
            print("Context: {ctx.flags}")
        ```
        """
        return _ContextFn(fn)

    def run(self, ctx = None):
        tstart = ticks_fn()
        
        if self._gen is None:
            if self._wants_context:
                result = self.update_fn(ctx)
            else:
                result = self.update_fn()
            # If it returned a generator, adopt it; otherwise treat as normal fn
            if hasattr(result, '__next__'):
                self._gen = result
            else:
                self._extra_delay = 0
                self.last_runtime = diff_fn(ticks_fn(), tstart)
                self.total_runs += 1
                self.total_runtime += self.last_runtime
                self.state = TaskState.SUCCEEDED

                return

        # Advance the generator one step
        if self._gen is not None:
            try:
                val = next(self._gen)
                if isinstance(val, WaitForTarget):
                    self.blocked_target = val.target_name
                    self.blocked_timeout = val.timeout_ms
                    self.blocked_start = ticks_fn()
                    self.state = TaskState.WAITING  # New state
                    self._extra_delay = 0

                    self.last_runtime = diff_fn(ticks_fn(), tstart)
                    self.total_runs += 1
                    self.total_runtime += self.last_runtime
                    return
                self._extra_delay = (val - self.interval_ms) if isinstance(val, int) else 0
                if self.state == TaskState.NOT_READY: self.state = TaskState.PENDING
            except StopIteration:
                self._gen = None
                self._extra_delay = 0
                self.state = TaskState.SUCCEEDED


        self.last_runtime = diff_fn(ticks_fn(), tstart)
        self.total_runs += 1
        self.total_runtime += self.last_runtime

class create_task(Task):
    def __init__(self, update_fn):
        super().__init__(update_fn=update_fn, interval_ms=0)

    def every(self, interval_ms):
        self.interval_ms = interval_ms
        return self

    def require(self, dependency):
        self.requires.append(dependency)
        return self

    def run_after(self, dependency):
        self.after.append(dependency)
        return self
    
    def run_unless(self, exclusion):
        self.unless.append(exclusion)
        return self

    def run_once(self):
        self.oneshot = True
        return self

    def run_immediately(self):
        self.next_run = ticks_fn()
        return self

    
class WaitForTarget:
    """Yield this to sleep until a target is dispatched"""
    def __init__(self, target_name, timeout_ms=None):
        self.target_name = target_name
        self.timeout_ms = timeout_ms
        self.timestamp = ticks_fn()

def stall(until, timeout = 20000, probe_interval = 0):
    now = ticks_fn()
    while not until():
        yield probe_interval
        if timeout and diff_fn(ticks_fn(), now) > timeout:
            raise TimeoutError("stall() Timed out")