class LogCapture:
    def __init__(self):
        self._records = []

    def get_records(self, when):
        return [r for r in self._records if r.get("when") == when]

    def clear(self):
        self._records.clear()
