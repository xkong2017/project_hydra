from fetcher import DataFetcher


class DataOrchestrator:
    def __init__(self):
        self._fetcher = DataFetcher()

    def get_items_by_type(self, item_type):
        result = self._fetcher.fetch("/api/items", params={"type": item_type})
        return result

    def get_all_items(self):
        result = self._fetcher.fetch("/api/items")
        return result

    def clear_cache(self):
        self._fetcher._cache.clear()
