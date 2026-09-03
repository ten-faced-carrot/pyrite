"""
Pyrite is a semi-competent implementation of several Scheduling Algorithms for Python/Micropython, mostly designed because Asyncio sucks balls to use.
"""


import time
import typing
import sys

from pyrite.logging import Logger
from pyrite.contextsys import SchedulingContext, _ContextFn
from pyrite.tasks import Task, create_task, WaitForTarget, stall
# NEW FOR SEPTEMBER '26! Pyrite now supports a functional API via pyrite.functional
from pyrite.compat import ticks_fn, ticks_add, diff_fn, print_exc_fn, sleep_ms
from pyrite.states import TaskState, MissedTickPolicy, ErrorPolicy
from pyrite.watchdog import Watchdog
from pyrite.schedulers import SimpleScheduling, Scheduler, PunitiveScheduling, Lock, Target