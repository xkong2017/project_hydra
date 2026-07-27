from cache import TimedCache


class DataFetcher:
    def __init__(self):
        self._cache = TimedCache()

    def fetch(self, url, params=None):
        cache_key = f"fetch:{url}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        raw_data = self._do_fetch(url, params)
        self._cache.set(cache_key, raw_data)
        return raw_data

    def _do_fetch(self, url, params):
        source = _SIMULATED_SOURCE.get(url, [])
        if params:
            return [item for item in source if item.get("type") == params.get("type", item.get("type"))]
        return list(source)


_SIMULATED_SOURCE = {
    "/api/items": [
        {"id": 1, "name": "apple", "type": "fruit"},
        {"id": 2, "name": "carrot", "type": "vegetable"},
        {"id": 3, "name": "banana", "type": "fruit"},
    ],
}
