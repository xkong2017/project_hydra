from counter import VisitCounter


class VisitDisplay:
    def __init__(self, counter):
        self._counter = counter

    def show_latest(self):
        return f"Visit #{self._counter.get_count()}"

    def show_log(self):
        raw = self._counter.get_log()
        display = [v + 1 for v in raw]
        return ", ".join(f"Visit #{v}" for v in display)
