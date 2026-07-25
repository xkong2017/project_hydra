from dbpool import DatabasePool, get_pool


def test_same_instance():
    a = get_pool()
    b = get_pool()
    assert a is b


def test_init_called_once():
    pool = get_pool(max_connections=5)
    assert pool.max_connections == 5
    pool2 = get_pool(max_connections=20)
    assert pool2.max_connections == 5, "Should not re-init with 20!"
