import threading
import time

# Counting semaphore with value 3
# Represents "3 free cores available"
sem = threading.Semaphore(3)

def job(name):
    print(f"{name} waiting for core...")
    sem.acquire()   # wait() — decrement
    print(f"{name} running on core")
    time.sleep(2)
    print(f"{name} done, releasing core")
    sem.release()   # signal() — increment

threads = []
for i in range(5):  # 5 jobs competing for 3 cores
    t = threading.Thread(target=job, args=(f"Job{i}",))
    threads.append(t)
    t.start()

for t in threads:
    t.join()
