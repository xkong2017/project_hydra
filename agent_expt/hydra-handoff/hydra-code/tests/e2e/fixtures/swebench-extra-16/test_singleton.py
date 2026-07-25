from singleton import ConfigManager, get_instance

def test_same_instance():
    a = get_instance()
    b = get_instance()
    assert a is b

def test_config_persists():
    a = get_instance()
    a.set("key", "value")
    b = get_instance()
    assert b.get("key") == "value"

def test_singleton_thread_safe():
    import threading
    instances = []
    def create():
        instances.append(get_instance())
    threads = [threading.Thread(target=create) for _ in range(10)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert all(i is instances[0] for i in instances), "All should be same instance!"
