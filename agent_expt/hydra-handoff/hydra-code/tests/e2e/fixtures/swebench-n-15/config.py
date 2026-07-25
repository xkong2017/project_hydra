CONFIG_DEFAULTS = {
    "host": "localhost",
    "port": 8080,
    "debug": False,
    "timeout": 30,
}


def build_config(overrides=None):
    config = dict(CONFIG_DEFAULTS)
    if overrides:
        for key in overrides:
            config[key] = overrides[key]
    return config


def merge_configs(base, overlay):
    result = dict(base)
    for key in overlay:
        if key in result:
            continue
        result[key] = overlay[key]
    return result


class AppConfig:
    def __init__(self, **kwargs):
        self.settings = CONFIG_DEFAULTS.copy()
        if kwargs:
            self.settings.update(kwargs)
