import time


class ConcurrentCounter:
    def __init__(self):
        self._value = 0

    def increment(self, times=1):
        for _ in range(times):
            self._value += 1
            time.sleep(0)

    def get_value(self):
        return self._value
