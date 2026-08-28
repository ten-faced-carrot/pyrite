from collections import deque

class defaultdict(dict):
    """
    Look. I know I said earlier that I like micropython but which godforsaken idiot came up with the idea that
    "Let's ship collections in micropython but also EXCLUDE defaultdict and make it an external dependency! What could ever go wrong???"

    Fuck you fuck you fuck you for making me write 7 lines. That's 7 lines I could've used to hit a drag on my vape and drink an energy. But no.

    May a thousand plagues fall unto thy bloodline.
    """
    def __init__(self, defaultvalue):
        super().__init__()
        self.defaultvalue = defaultvalue

    def __getitem__(self, key):
        if key not in self:
            self[key] = self.defaultvalue
        return super().__getitem__(key)

class LocksControl: # TODO i promise this will be completed
    def __init__(self):
        self.locked_resources = set()

    def lock(self, resource):
        if resource in self.locked_resources:
            raise RuntimeError(f"Tried to aquire lock for {resource} but it is already locked!")
        self.locked_resources.add(resource)

    def unlock(self, resource):
        if resource not in self.locked_resources:
            raise RuntimeError(f"Tried to unlock {resource} but it is not locked!")
        self.locked_resources.remove(resource)

    def is_locked(self, resource):
        return resource in self.locked_resources

class SchedulingContext:
    def __init__(self):
        self.message_queue = deque([], 5)
        self.flags = defaultdict(None)
        self.__dispatched_targets = set() # Meh. Still looking for a better way to do this, if there is one
        self.locks = LocksControl()

    def dispatch_target(self, name):
        self.dispatched_targets.add(name)

    @property
    def dispatched_targets(self):
        return self.__dispatched_targets

    def clear(self):
        
        while self.message_queue: self.message_queue.pop()
        self.flags.clear()

    def push_msg(self, msg):
        self.message_queue.append(msg)
    
    def pop_msg(self):
        if self.message_queue:
            return self.message_queue.popleft()
        return None

    def peek_msg(self):
        if self.message_queue:
            return self.message_queue[0]
        return None
    
    def set_flag(self, name, value=True):
        self.flags[name] = value

    def clear_flag(self, name):
        self.flags[name] = None

    def is_flag_set(self, name):
        return self.flags.get(name) is not None
    
    def get_flag(self, name):
        return self.flags.get(name)
    
class _ContextFn:
    def __init__(self, fn):
        self.fn = fn
        self.__name__ = self.fn.__name__

    def __call__(self, ctx):
        return self.fn(ctx)