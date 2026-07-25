from events import EventStore, EventProcessor


def test_add_and_count():
    store = EventStore(max_events=5)
    for i in range(3):
        store.add({"id": i})
    assert store.count() == 3


def test_trim_old_events():
    store = EventStore(max_events=5)
    for i in range(10):
        store.add({"id": i})
    assert store.count() == 5, f"Expected 5 events, got {store.count()}"


def test_get_recent():
    store = EventStore(max_events=20)
    for i in range(10):
        store.add({"id": i, "type": "test"})
    recent = store.get_recent(3)
    assert len(recent) == 3
    assert recent[-1]["id"] == 9


def test_processor_trims():
    proc = EventProcessor()
    for i in range(200):
        proc.process({"id": i})
    assert len(proc._processed) <= 100
