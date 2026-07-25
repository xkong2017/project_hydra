class ConfigManager:
    def __new__(cls):
        instance = super().__new__(cls)
        instance._config = {}
        return instance
    def get(self, key, default=None):
        return self._config.get(key, default)
    def set(self, key, value):
        self._config[key] = value

def get_instance():
    return ConfigManager()
