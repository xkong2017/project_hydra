import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from counter import VisitCounter
from display import VisitDisplay


@pytest.fixture
def system():
    counter = VisitCounter()
    display = VisitDisplay(counter)
    return counter, display


class TestSystem:
    def test_record_visit_returns_correct_sequence(self, system):
        counter, _ = system
        assert counter.record_visit() == 1
        assert counter.record_visit() == 2
        assert counter.record_visit() == 3

    def test_get_count_is_consistent(self, system):
        counter, _ = system
        counter.record_visit()
        counter.record_visit()
        assert counter.get_count() == 2

    def test_log_matches_recorded_visits(self, system):
        counter, _ = system
        counter.record_visit()
        counter.record_visit()
        counter.record_visit()
        assert counter.get_log() == [1, 2, 3]

    def test_display_consistency(self, system):
        counter, display = system
        for _ in range(3):
            counter.record_visit()
        log_display = display.show_log()
        assert "Visit #1" in log_display
        assert "Visit #2" in log_display
        assert "Visit #3" in log_display
