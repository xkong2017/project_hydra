import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import pytest
from engine import ScoringEngine
from processor import GradeProcessor


CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


class TestScoring:
    def test_engine_max_score(self):
        engine = ScoringEngine(CONFIG_PATH)
        record = {"age": 25, "score": 95, "has_id": True}
        score = engine.score(record)
        assert score <= 35

    def test_engine_no_overflow_for_80_no_id(self):
        engine = ScoringEngine(CONFIG_PATH)
        record = {"age": 25, "score": 80, "has_id": False}
        score = engine.score(record)
        assert score == 30

    def test_grade_b_for_80_no_id(self):
        processor = GradeProcessor()
        results = processor.evaluate(CONFIG_PATH, [
            {"name": "Alice", "age": 25, "score": 80, "has_id": False}
        ])
        assert results[0]["grade"] == "B"
        assert results[0]["score"] == 30

    def test_grade_a_for_max(self):
        processor = GradeProcessor()
        results = processor.evaluate(CONFIG_PATH, [
            {"name": "Bob", "age": 25, "score": 95, "has_id": True}
        ])
        assert results[0]["grade"] == "A"
        assert results[0]["score"] == 35
