
class Target: # Fuck you *installs SystemD on your esp32*
    def __init__(self, name):
        self.name = name

class Lock: # Same abstraction as Target. I don't know what abstraction means but it feels fitting.
    def __init__(self, resource):
        self.name = resource

