class DataProcessor:
    def uppercase_names(self, records):
        for rec in records:
            if len(rec) > 0:
                rec[0] = rec[0].upper()
        return records

    def strip_emails(self, records):
        result = []
        for rec in records:
            if len(rec) > 2:
                email = rec[2]
                rec[2] = email.strip().lower()
            result.append(rec)
        return result
