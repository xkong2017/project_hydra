import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import threading
import pytest
from counter_conc import ConcurrentCounter
from stats import StatsCollector


@pytest.fixture
def counter():
    return ConcurrentCounter()


@pytest.fixture
def collector(counter):
    return StatsCollector(counter)


class TestConcurrent:
    def test_single_thread_increment(self, counter):
        counter.increment(5)
        assert counter.get_value() == 5

    def test_concurrent_safety(self, counter):
        thread_count = 10
        increments_per_thread = 1000
        threads = []

        def hammer():
            for _ in range(increments_per_thread):
                counter.increment(1)

        for _ in range(thread_count):
            t = threading.Thread(target=hammer)
            threads.append(t)

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counter.get_value() == thread_count * increments_per_thread

    def test_stats_average_is_one(self, counter, collector):
        avg = collector.average_increments(5)
        assert avg == 1.0

    def test_stats_after_concurrent(self, counter, collector):
        thread_count = 5
        target_per_thread = 200
        threads = []
        for _ in range(thread_count):
            t = threading.Thread(target=collector.average_increments, args=(target_per_thread,))
            threads.append(t)
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        final_value = counter.get_value()
        assert final_value == thread_count * target_per_thread
        assert collector.average_increments(1) == 1.0
