from validator import validate_email, validate_username, validate_password


def test_valid_email():
    assert validate_email("user@example.com")


def test_email_no_at():
    assert not validate_email("userexample.com")


def test_email_no_domain():
    assert not validate_email("user@.com")


def test_email_no_tld():
    assert not validate_email("user@example"), "Email without TLD should be invalid"


def test_email_with_dot_in_local():
    assert validate_email("first.last@example.com")


def test_email_space_in_domain():
    assert not validate_email("user@exa mple.com"), "Domain with spaces should be invalid"


def test_email_no_local():
    assert not validate_email("@example.com")


def test_username_valid():
    assert validate_username("alice")


def test_username_too_short():
    assert not validate_username("ab")


def test_password_valid():
    assert validate_password("Secure1pass")
