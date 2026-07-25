class ItemCache:
    def __init__(self):
        self._store = {}

    def add(self, item):
        if item.category not in self._store:
            self._store[item.category] = []
        self._store[item.category].append(item)

    def get_items(self, category, seen=None):
        if seen is None:
            seen = []
        result = []
        for item in self._store.get(category, []):
            if item.id not in seen:
                seen.append(item.id)
                result.append(item)
        return result


class Item:
    def __init__(self, id, category, name):
        self.id = id
        self.category = category
        self.name = name
