from cache import Item, ItemCache


def test_get_items_once():
    c = ItemCache()
    c.add(Item(1, "a", "x"))
    c.add(Item(2, "a", "y"))
    assert len(c.get_items("a")) == 2


def test_get_items_twice_is_idempotent():
    c = ItemCache()
    c.add(Item(1, "a", "x"))
    c.get_items("a")
    second = c.get_items("a")
    assert len(second) == 0


def test_get_items_different_categories():
    c = ItemCache()
    c.add(Item(1, "a", "x"))
    c.add(Item(2, "b", "y"))
    assert len(c.get_items("a")) == 1
    assert len(c.get_items("b")) == 1


def test_get_items_independent_calls():
    c = ItemCache()
    c.add(Item(1, "a", "x"))
    c.add(Item(2, "a", "y"))
    first = c.get_items("a")
    second = c.get_items("a")
    # Each call should return only unseen items
    assert len(first) == 2
    assert len(second) == 0
