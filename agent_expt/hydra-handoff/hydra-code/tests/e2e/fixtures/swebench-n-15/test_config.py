from config import build_config, merge_configs, AppConfig, CONFIG_DEFAULTS


def test_defaults():
    cfg = build_config()
    assert cfg["host"] == "localhost"
    assert cfg["port"] == 8080


def test_override_port():
    cfg = build_config({"port": 9090})
    assert cfg["port"] == 9090
    assert cfg["host"] == "localhost"


def test_override_debug():
    cfg = build_config({"debug": True, "timeout": 60})
    assert cfg["debug"] is True
    assert cfg["timeout"] == 60


def test_merge_configs():
    base = {"a": 1, "b": 2}
    overlay = {"b": 3, "c": 4}
    result = merge_configs(base, overlay)
    assert result == {"a": 1, "b": 3, "c": 4}


def test_appconfig_override():
    cfg = AppConfig(port=3000, debug=True)
    assert cfg.settings["port"] == 3000
    assert cfg.settings["debug"] is True
    assert cfg.settings["host"] == "localhost"
