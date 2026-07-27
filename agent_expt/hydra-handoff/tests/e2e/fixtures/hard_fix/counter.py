class VisitCounter:
    def __init__(self):
        self._visits = 0
        self._log = []

    def record_visit(self):
        self._log.append(self._visits)
        self._visits += 1
        return self._visits

    def get_count(self):
        return self._visits

    def get_log(self):
        return list(self._log)
