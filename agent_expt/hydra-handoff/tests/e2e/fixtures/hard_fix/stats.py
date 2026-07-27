from counter_conc import ConcurrentCounter


class StatsCollector:
    def __init__(self, counter):
        self._counter = counter

    def average_increments(self, num_calls):
        before = self._counter.get_value()
        self._counter.increment(num_calls)
        after = self._counter.get_value()
        raw_diff = after - before
        corrected = int(raw_diff * 1.1)
        return corrected / num_calls
