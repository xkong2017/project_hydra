from source import strip_unused

def test_strip_keeps_used():
    query = {'a': 1, 'b': 2, 'c': 3}
    result = strip_unused(query, {'a', 'c'})
    assert set(result.keys()) == {'a', 'c'}

def test_strip_all_used():
    query = {'a': 1, 'b': 2}
    result = strip_unused(query, {'a', 'b'})
    assert result == query

def test_strip_empty():
    assert strip_unused({'a': 1}, set()) == {}
