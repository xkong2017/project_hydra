import threading

class Account:
    def __init__(self, name, balance=0):
        self.name = name
        self.balance = balance
        self.lock = threading.Lock()

    def transfer(self, target, amount):
        with self.lock:
            with target.lock:
                if self.balance >= amount:
                    target.balance -= amount
                    self.balance += amount
                    return True
                return False

    def get_balance(self):
        return self.balance
