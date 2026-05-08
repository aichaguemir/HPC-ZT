# save as memory_test.py
import os

shared_value = 100

pid = os.fork()

if pid == 0:
    # Child changes the value
    shared_value = 999
    print(f"Child sees: {shared_value}")  # prints 999
    os._exit(0)
else:
    os.wait()
    print(f"Parent sees: {shared_value}")  # still prints 100!
