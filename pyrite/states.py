
class MissedTickPolicy:
    """
    Tells the Scheduler how to handle missed Executions.

    SKIP: Just ignore the skipped executions and continue normally
    BURST: Run the Task until it finished executing as many times as it missed
    """

    SKIP = 0
    BURST = 1

class ErrorPolicy:
    """
    Tells the Scheduler how to handle crashed Tasks. Can either be supplied as an argument to the Scheduler or to a task. The Scheduler prefers the Tasks choice over its own.
    CRASH   : The scheduler crashes, resetting the board to a clean state. This is the default when creating a Scheduler.
    DISABLE : Disables the Erroring Task
    RETRY   : The Scheduler will attempt to run the Task in the next cycle
    BACKOFF : The Scheduler runs a crashing function less and wait between two consecutive attempts. To avoid any kind of memory overflow, this caps out at 256s.
    INHERIT : ONLY to be used inside a Task Object, tells the Scheduler that the Task has no specific Preference on how to handle Errors and will comply with the scheduler's preference.
    """
    CRASH = -1
    DISABLE = 0
    RETRY = 1
    BACKOFF = 2
    INHERIT = 3

class TaskState:
    """
    Task-Internal State that shows how the task is doing. Useful for debugging, and also for ordering.
    """
    DISABLED = -1
    NOT_READY = 0
    PENDING = 1
    WAITING = 2
    SUCCEEDED = 3
    CRASHED = -2
