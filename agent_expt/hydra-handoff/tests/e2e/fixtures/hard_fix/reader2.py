class DataReader:
    def __init__(self):
        self._records = []

    def read_line(self, line):
        if not line.strip():
            return
        parts = line.strip().split(",")
        self._records.append(parts)

    def get_records(self):
        return self._records

    def get_record_count(self):
        return len(self._records)
