import numpy as np

# Create large matrices (example: 1000 x 1000)
size = 1000

A = np.random.rand(size, size)
B = np.random.rand(size, size)

# Matrix multiplication
result = A @ B   # same as np.dot(A, B)

print(result.shape)
