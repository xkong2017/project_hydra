from source import Blueprint

def test_blueprint_name_required():
    try:
        b = Blueprint("", "test")
        assert False, "Should have raised"
    except ValueError:
        pass

def test_blueprint_valid():
    b = Blueprint("auth", "auth.routes")
    assert b.name == "auth"
