def format_legend_value(val):
    if val >= 1000:
        return f"{val/1000:.1f}K"
    elif val >= 1000000:
        return f"{val/1000000:.1f}M"
    return str(val)

def format_legend(values):
    return [format_legend_value(v) for v in values]
