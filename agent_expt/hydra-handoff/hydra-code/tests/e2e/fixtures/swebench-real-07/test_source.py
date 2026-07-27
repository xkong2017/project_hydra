import numpy as np
from source import preserve_dtype

class Transformer:
    def __init__(self, preserve):
        self._preserve_dtype = preserve

def test_preserves_dtype():
    t = Transformer(preserve=True)
    X = np.array([[1, 2], [3, 4]], dtype=np.int64)
    result = preserve_dtype(t, X)
    assert result.dtype == np.int64, f"Expected int64, got {result.dtype}"
