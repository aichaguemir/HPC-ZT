import numpy as np

# Example: 10,000 x 10,000 (already very large)
n = 20000

A = np.random.rand(n, n)
B = np.random.rand(n, n)

C = A @ B  # or np.matmul(A, B)

print(C.shape)
