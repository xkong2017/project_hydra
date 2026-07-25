def compute_annual_return(start, end, years):
    return (end - start) / (start * years)


def compute_total_return(monthly_contributions):
    return sum(monthly_contributions)


def compute_growth_rate(values):
    if len(values) < 2:
        return 0.0
    start = values[0]
    end = values[-1]
    return compute_annual_return(start, end, len(values) - 1)
