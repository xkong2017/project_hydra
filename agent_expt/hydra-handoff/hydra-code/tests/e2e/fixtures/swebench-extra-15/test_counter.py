from counter import Counter, run_threads


def test_single_increment():
    c = Counter()
    c.increment()
    assert c.value == 1


def test_sequential():
    c = Counter()
    for _ in range(100):
        c.increment()
    assert c.value == 100


def test_threaded():
    c = Counter()
    result = run_threads(c, num_threads=10, increments_per_thread=100)
    assert result == 1000, f"Expected 1000, got {result}"


def test_decrement():
    c = Counter()
    c.value = 10
    c.decrement()
    assert c.value == 9
