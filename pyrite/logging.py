import sys

class Logger:
    ERROR = 1
    WARN  = 2
    INFO  = 3

    def __init__(self, level, file=sys.stdout):
        self.level = level
        self.file = file

    def info(self, msg):
        if self.level > self.WARN:
            print(f"[INFO] {msg}", file=self.file)
    def warn(self, msg):
        if self.level > self.ERROR:
            print(f"[WARN] {msg}", file=self.file)
    def error(self, msg):
        print(f"[ERROR] {msg}", file=self.file)
    