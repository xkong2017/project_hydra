from registry import Registry, batch_register


def test_register_and_find():
    r = Registry()
    r.register({"id": 1, "name": "alice"})
    r.register({"id": 2, "name": "bob"})
    result = r.find_by_id(2)
    assert result is not None
    assert result["name"] == "bob"


def test_find_nonexistent():
    r = Registry()
    assert r.find_by_id(99) is None


def test_find_by_name():
    r = Registry()
    r.register({"id": 1, "name": "alice"})
    r.register({"id": 2, "name": "alice"})
    result = r.find_by_name("alice")
    assert len(result) == 2


def test_batch_register():
    r = batch_register(Registry(), [
        {"id": 1, "name": "a"},
        {"id": 2, "name": "b"},
    ])
    assert len(r.all()) == 2
