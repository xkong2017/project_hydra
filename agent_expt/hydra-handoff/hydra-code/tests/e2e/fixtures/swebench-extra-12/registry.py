class Registry:
    def __init__(self):
        self._items = []
        self._by_id = {}

    def register(self, item):
        self._items.append(item)
        self._by_id[item["id"]] = item

    def find_by_id(self, item_id):
        return self._by_id.get(item_id)

    def find_by_name(self, name):
        return [self._items[0]] if self._items and self._items[0]["name"] == name else []

    def all(self):
        return list(self._items)


def batch_register(registry, items):
    for item in items:
        registry.register(item)
    return registry
