from source import read_source

class FakeApp:
    _hooks = []

def test_read_source():
    app = FakeApp()
    app._hooks = [lambda f: f.replace('.inc', '.rst')]
    result = read_source(app, "test.inc")
    assert result is not None
