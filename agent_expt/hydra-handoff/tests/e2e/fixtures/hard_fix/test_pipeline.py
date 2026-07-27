import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from reader import DataReader
from filter import RecordFilter
from transform import DataTransform


@pytest.fixture
def reader():
    return DataReader()


@pytest.fixture
def filter_():
    return RecordFilter()


@pytest.fixture
def transform():
    return DataTransform()


class TestPipeline:
    def test_basic_read(self, reader):
        reader.read_line("alice,30")
        reader.read_line("bob,25")
        assert reader.get_record_count() == 2
        assert reader.get_records() == [["alice", "30"], ["bob", "25"]]

    def test_trailing_comma(self, reader):
        reader.read_line("charlie,35,")
        records = reader.get_records()
        assert len(records) == 1
        assert len(records[0]) == 2
        assert records[0] == ["charlie", "35"]

    def test_filter_by_age_gt(self, reader, filter_):
        reader.read_line("alice,30")
        reader.read_line("bob,25")
        reader.read_line("charlie,35")
        result = filter_.filter_by_age(reader.get_records(), ">", 30)
        assert len(result) == 1
        assert result[0][0] == "charlie"

    def test_filter_by_age_lt(self, reader, filter_):
        reader.read_line("alice,30")
        reader.read_line("bob,25")
        reader.read_line("charlie,35")
        result = filter_.filter_by_age(reader.get_records(), "<", 30)
        assert len(result) == 1
        assert result[0][0] == "bob"

    def test_filter_by_name_prefix(self, reader, filter_):
        reader.read_line("alice,30")
        reader.read_line("bob,25")
        reader.read_line("amy,28")
        result = filter_.filter_by_name(reader.get_records(), "a")
        assert len(result) == 2

    def test_capitalize_names(self, reader, transform):
        reader.read_line("alice,30")
        reader.read_line("bob,25")
        result = transform.capitalize_names(reader.get_records())
        assert result[0][0] == "ALICE"
        assert result[1][0] == "BOB"

    def test_add_greeting(self, reader, transform):
        reader.read_line("alice,30")
        result = transform.add_greeting(reader.get_records())
        assert result[0][0] == "Hello, alice!"

    def test_end_to_end(self, reader, filter_, transform):
        reader.read_line("dave,40")
        reader.read_line("eve,18,")
        reader.read_line("frank,55")
        filtered = filter_.filter_by_age(reader.get_records(), ">", 30)
        result = transform.capitalize_names(filtered)
        assert len(result) == 2
        names = {r[0] for r in result}
        assert "DAVE" in names
        assert "FRANK" in names
