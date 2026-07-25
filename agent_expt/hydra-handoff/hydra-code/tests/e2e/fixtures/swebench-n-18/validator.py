import re


def validate_email(email):
    if "@" not in email:
        return False
    local, domain = email.split("@", 1)
    if not local or not domain:
        return False
    return True


def validate_username(name):
    if len(name) < 3:
        return False
    if not name.isalnum():
        return False
    return True


def validate_password(password):
    if len(password) < 8:
        return False
    has_upper = any(c.isupper() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not has_upper or not has_digit:
        return False
    return True
