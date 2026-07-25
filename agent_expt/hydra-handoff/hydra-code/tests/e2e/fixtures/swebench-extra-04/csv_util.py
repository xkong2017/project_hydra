def parse_csv_line(line):
    return line.strip().split(",")


def parse_csv(text):
    lines = text.strip().split("\n")
    return [parse_csv_line(line) for line in lines]


def to_csv_row(values):
    escaped = []
    for v in values:
        s = str(v)
        if "," in s or '"' in s:
            s = '"' + s.replace('"', '""') + '"'
        escaped.append(s)
    return ",".join(escaped)
