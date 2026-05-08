# mpi_test.py
from mpi4py import MPI
import numpy as np

comm = MPI.COMM_WORLD
rank = comm.Get_rank()
size = comm.Get_size()

print(f"[Rank {rank}/{size}] running on {MPI.Get_processor_name()}")

local_sum = sum(range(rank * 10, (rank + 1) * 10))
total = comm.reduce(local_sum, op=MPI.SUM, root=0)

if rank == 0:
    print(f"Total sum across all ranks: {total}")
    print(f"MPI test completed with {size} processes")
