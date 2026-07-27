class RecordFilter:
    def filter_by_age(self, records, op, threshold):
        result = []
        for rec in records:
            if len(rec) < 2:
                continue
            age_str = rec[1]
            if op == ">":
                if age_str > threshold:
                    result.append(rec)
            elif op == "<":
                if age_str < threshold:
                    result.append(rec)
            elif op == "==":
                if age_str == str(threshold):
                    result.append(rec)
        return result

    def filter_by_name(self, records, prefix):
        result = []
        for rec in records:
            if len(rec) < 1:
                continue
            if rec[0].startswith(prefix):
                result.append(rec)
        return result
