from pyrite import *
from machine import Pin

led = Pin("LED", Pin.OUT)
def led_task():
   led.toggle()
def simple_task():
  print("Hello world")

tasks = [Task(led_task, 500), Task(simple_task, 1000)]
sched = Scheduler(SimpleScheduling) # We don't need the Overhead from PunitiveScheduling here as none of our Tasks has the option of stalling anywhere.
# If you were using a lot of Sensors, conisder replacing SimpleScheduling with PunitiveScheduling
sched.add_tasks(tasks)
sched.run_forever()

