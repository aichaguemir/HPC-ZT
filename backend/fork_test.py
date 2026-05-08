# save as fork_test.py and run it
import os

print(f"Before fork: PID={os.getpid()}")

pid = os.fork()

if pid == 0:
    # This code runs in the CHILD process
    print(f"Child: PID={os.getpid()}, Parent={os.getppid()}")
    os._exit(0)
else:
    # This code runs in the PARENT process
    print(f"Parent: PID={os.getpid()}, Child PID={pid}")
    os.wait()  # wait for child to finish (join)
    print("Parent: child finished")
    
