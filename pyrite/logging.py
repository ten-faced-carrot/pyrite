class Logger:
    ERROR = 1
    WARN  = 2
    INFO  = 3

    def __init__(self, level):
        self.level = level

    def info(self, msg):
        if self.level > self.WARN:
            print(f"[INFO] {msg}")
    def warn(self, msg):
        if self.level > self.ERROR:
            print(f"[WARN] {msg}")
    def error(self, msg):
        print(f"[ERROR] {msg}")
    