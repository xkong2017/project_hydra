def round_half_up(value, decimals=0):
    factor = 10 ** decimals
    return round(value * factor) / factor


def round_half_down(value, decimals=0):
    factor = 10 ** decimals
    return int(value * factor) / factor


def round_to_nearest(value, nearest=0.05):
    return round(value / nearest) * nearest


def calculate_tax(amount, rate=0.07):
    return round_half_up(amount * rate, 2)
