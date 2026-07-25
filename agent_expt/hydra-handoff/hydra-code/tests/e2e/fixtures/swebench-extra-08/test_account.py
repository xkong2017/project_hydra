import pytest
from account import BankAccount


def test_deposit():
    acc = BankAccount()
    acc.deposit(100)
    assert acc.balance == 100


def test_withdraw():
    acc = BankAccount(100)
    acc.withdraw(50)
    assert acc.balance == 50


def test_balance_setter_rejects_negative():
    acc = BankAccount(100)
    with pytest.raises(ValueError, match="negative|invalid"):
        acc.balance = -50


def test_balance_setter_allows_zero():
    acc = BankAccount()
    acc.balance = 0
    assert acc.balance == 0
