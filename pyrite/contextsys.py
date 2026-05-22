from collections import deque

class defaultdict(dict):
    def __init__(self, defaultvalue):
        super().__init__()
        self.defaultvalue = defaultvalue

    def __getitem__(self, key):
        if key not in self:
            self[key] = self.defaultvalue
        return super().__getitem__(key)


class SchedulingContext:
    def __init__(self):
        self.message_queue = deque([], 5)
        self.flags = defaultdict(None)

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