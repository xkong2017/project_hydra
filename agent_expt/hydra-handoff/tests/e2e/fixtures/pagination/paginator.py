class Paginator:
    def __init__(self, items, per_page=10):
        self.items = items
        self.per_page = per_page
        self.total_pages = (len(items) + per_page - 1) // per_page

    def get_page(self, page):
        if page < 1 or page > self.total_pages:
            raise ValueError(f"Page {page} out of range (1-{self.total_pages})")
        start = (page - 1) * self.per_page
        end = start + self.per_page
        return self.items[start:end]