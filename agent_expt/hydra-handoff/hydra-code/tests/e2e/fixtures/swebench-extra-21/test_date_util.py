from date_util import format_date, parse_date, days_between, is_weekend


def test_format():
    assert format_date(2024, 3, 5) == "2024-03-05"


def test_parse():
    assert parse_date("2024-03-05") == (2024, 3, 5)


def test_days_between():
    assert days_between((2024, 1, 1), (2024, 1, 10)) == 9


def test_is_weekend_saturday():
    assert is_weekend(2024, 3, 30) is True  # Saturday


def test_is_weekend_monday():
    assert is_weekend(2024, 4, 1) is False  # Monday
