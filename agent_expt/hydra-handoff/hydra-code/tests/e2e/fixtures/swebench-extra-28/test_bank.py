from bank import Account

def test_transfer():
    a = Account("A", 100)
    b = Account("B", 0)
    result = a.transfer(b, 50)
    assert result is True
    assert a.get_balance() == 50, f"Expected A=50, got {a.get_balance()}"
    assert b.get_balance() == 50, f"Expected B=50, got {b.get_balance()}"

def test_insufficient():
    a = Account("A", 10)
    b = Account("B", 0)
    result = a.transfer(b, 20)
    assert result is False

def test_transfer_reverses():
    a = Account("A", 100)
    b = Account("B", 50)
    a.transfer(b, 30)
    # A should lose 30
    assert a.get_balance() == 70, f"Expected A=70, got {a.get_balance()}"
    # B should gain 30
    assert b.get_balance() == 80, f"Expected B=80, got {b.get_balance()}"
