from merger import deep_merge, merge_configs


def test_simple_merge():
    result = deep_merge({"a": 1}, {"b": 2})
    assert result == {"a": 1, "b": 2}


def test_nested_merge():
    result = deep_merge({"db": {"host": "a"}}, {"db": {"port": 5432}})
    assert result == {"db": {"host": "a", "port": 5432}}


def test_list_concat():
    result = deep_merge({"tags": [1, 2]}, {"tags": [3, 4]})
    assert result == {"tags": [1, 2, 3, 4]}, f"Got {result}"


def test_list_single():
    result = deep_merge({"items": [1]}, {"items": [2]})
    assert result == {"items": [1, 2]}


def test_config_merge():
    defaults = {"plugins": ["a"], "debug": False}
    user = {"plugins": ["b"], "debug": True}
    result = merge_configs(defaults, user)
    assert result["plugins"] == ["a", "b"]
    assert result["debug"] is True
