try:
    import _thread
    threading_available = True
except ImportError:
    threading_available = False # Too bad so sad no watchdog for you thats what you get for using old-ass micropython that doesn't even have that. I'm sorry.

try:
    import machine
    reset = machine.reset
except ImportError:
    import os
    def reset(): 
        print("Watchdog triggered!")
        os._exit(1)
from pyrite.compat import ticks_fn, diff_fn, sleep_ms


class Watchdog:
    def __init__(self):
        self.last_ping = ticks_fn()
        self.alive = False
        self.timeout = 20000

    def enable(self):
        if not threading_available:
            raise SystemError("No Threading available!")
        self.alive = True
        self.last_ping = ticks_fn()

    def cycle(self):
        while self.alive:
            if diff_fn(ticks_fn(), self.last_ping) > self.timeout:
                reset()
            sleep_ms(100)

    def heartbeat(self):
        self.last_ping = ticks_fn()

    def start(self):

        if not threading_available:
            raise SystemError("No Threading available!")
        _thread.start_new_thread(self.cycle, ())