import pytest
from tests.e2e.fixtures.pagination.paginator import Paginator


@pytest.fixture
def sample_items():
    return list(range(1, 26))  # 25 items


class TestPaginator:
    def test_page_1_returns_first_page(self, sample_items):
        p = Paginator(sample_items, per_page=10)
        assert p.get_page(1) == [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

    def test_page_2_returns_second_page(self, sample_items):
        p = Paginator(sample_items, per_page=10)
        assert p.get_page(2) == [11, 12, 13, 14, 15, 16, 17, 18, 19, 20]

    def test_last_page_returns_remaining(self, sample_items):
        p = Paginator(sample_items, per_page=10)
        assert p.get_page(3) == [21, 22, 23, 24, 25]

    def test_total_pages_correct(self, sample_items):
        p = Paginator(sample_items, per_page=10)
        assert p.total_pages == 3

    def test_out_of_range_page_raises(self, sample_items):
        p = Paginator(sample_items, per_page=10)
        with pytest.raises(ValueError):
            p.get_page(0)
        with pytest.raises(ValueError):
            p.get_page(4)

    def test_exact_multiple_items(self):
        items = list(range(1, 21))  # 20 items
        p = Paginator(items, per_page=10)
        assert p.total_pages == 2
        assert p.get_page(1) == list(range(1, 11))
        assert p.get_page(2) == list(range(11, 21))

    def test_single_per_page(self, sample_items):
        p = Paginator(sample_items, per_page=1)
        assert p.total_pages == 25
        assert p.get_page(1) == [1]
        assert p.get_page(25) == [25]