"""Read-only dictionary wrapper.

BUGGY: Delegates __getitem__, __contains__, keys(), __len__, __iter__
to the inner dict, but MISSES get(), values(), and items(). These
fall through to dict's default implementation which accesses the
wrapper's OWN empty dict instead of the wrapped data.
FIX: Also delegate get(), values(), and items().
"""


class ReadOnlyDict:
    """A read-only view into a dictionary."""

    def __init__(self, data: dict):
        self._data = data

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    def keys(self):
        return self._data.keys()

    def __len__(self):
        return len(self._data)

    def __iter__(self):
        return iter(self._data)

    # BUG: get(), values(), items() are NOT delegated.
    # They fall through to the default dict behavior which
    # accesses the ReadOnlyDict instance's own __dict__ (empty),
    # not self._data.
