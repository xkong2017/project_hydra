from source import format_legend

def test_small():
    assert format_legend([1, 2, 3]) == ["1", "2", "3"]

def test_thousands():
    assert format_legend([1500, 25000]) == ["1.5K", "25.0K"]

def test_millions():
    result = format_legend([1500000, 20000000])
    assert result == ["1.5M", "20.0M"]
