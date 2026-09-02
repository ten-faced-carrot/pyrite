import sys
import time

if hasattr(sys, "print_exception"):
    print_exc_fn = sys.print_exception
else:
    import traceback
    print_exc_fn = traceback.print_exception 
# I'm aware that this isn't "returning" the traceback, it only prints it out. Go cry elsewhere don't mansplain to me

if hasattr(time, "ticks_ms"):
    ### MicroPython Environment
    ticks_fn = time.ticks_ms
    diff_fn = time.ticks_diff
    ticks_add = time.ticks_add
    sleep_ms = time.sleep_ms
else:
    """
    Reinventing the wheel because Micropython's Time Library is objectively better than CPythons, fight me
    """
    ticks_fn = lambda: int(time.monotonic() * 1000)
    diff_fn = lambda a, b: a - b
    ticks_add = lambda a, b: a+b
    sleep_ms = lambda m: time.sleep(m/1000)