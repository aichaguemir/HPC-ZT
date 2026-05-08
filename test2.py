import numpy as np

# Define size of large matrices
rows, cols = 100, 100  # you can increase this (e.g., 500, 1000)

# Generate random matrices
A = np.random.randint(0, 10, (rows, cols))
B = np.random.randint(0, 10, (cols, rows))

# Perform matrix multiplication
C = np.dot(A, B)

# Print result
print("Matrix A:\n", A)
print("\nMatrix B:\n", B)
print("\nResult (A x B):\n", C)
