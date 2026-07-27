class DataTransform:
    def capitalize_names(self, records):
        result = []
        for rec in records:
            if len(rec) < 1:
                continue
            name = rec[0]
            rec[0] = name.upper()
            result.append(rec)
        return result

    def add_greeting(self, records):
        result = []
        for rec in records:
            greeting = f"Hello, {rec[0]}!"
            result.append([greeting] + rec)
        return result
