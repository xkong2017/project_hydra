import numpy as np

def preserve_dtype(transformer, X):
    return X.astype(np.float64)
