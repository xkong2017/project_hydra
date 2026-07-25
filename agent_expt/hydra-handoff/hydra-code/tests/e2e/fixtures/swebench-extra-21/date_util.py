def format_date(year, month, day):
    return f"{month:02d}/{day:02d}/{year}"


def parse_date(text):
    parts = text.split("-")
    return int(parts[0]), int(parts[1]), int(parts[2])


def days_between(d1, d2):
    from datetime import date
    a = date(*d1)
    b = date(*d2)
    return abs((b - a).days)


def is_weekend(year, month, day):
    from datetime import date
    return date(year, month, day).weekday() >= 5
