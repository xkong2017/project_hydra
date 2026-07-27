TIER_THRESHOLDS = [0, 100, 500, 2000]
TIER_DISCOUNTS = [0.0, 0.05, 0.10, 0.20]


def get_tier(total_spent):
    for i in range(len(TIER_THRESHOLDS) - 1, -1, -1):
        if total_spent >= TIER_THRESHOLDS[i]:
            return i
    return 0


def apply_discount(price, total_spent):
    tier = get_tier(total_spent)
    discount = TIER_DISCOUNTS[tier]
    return price * (1 - discount)


def apply_bulk_discount(quantity, unit_price):
    if quantity >= 100:
        return quantity * unit_price * 0.8
    elif quantity >= 50:
        return quantity * unit_price * 0.85
    elif quantity >= 10:
        return quantity * unit_price * 0.9
    return quantity * unit_price


def calculate_total(item_prices, quantities, total_spent):
    total = 0.0
    for price, qty in zip(item_prices, quantities):
        bulk = apply_bulk_discount(qty, price)
        tier_discounted = apply_discount(bulk, total_spent)
        total += tier_discounted
    return total
