import numpy as np

chunk_id = __CHUNK_ID__
total_chunks = __TOTAL_CHUNKS__

rows  = 500 // total_chunks
start = (chunk_id - 1) * rows
end   = start + rows

A = np.random.rand(end - start, 200)
B = np.random.rand(200, 200)
C = np.dot(A, B)

print(f"Chunk {chunk_id}/{total_chunks}: rows {start}-{end}, shape={C.shape}")
