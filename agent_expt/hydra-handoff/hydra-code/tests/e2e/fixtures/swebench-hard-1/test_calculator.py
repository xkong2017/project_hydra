"""Tests for calculator operation factory."""
from calculator import make_operations


def test_add1():
    """add1 should add 1 to its argument."""
    ops = dict(make_operations())
    assert ops["add1"](5) == 6


def test_add3():
    """add3 should add 3 to its argument."""
    ops = dict(make_operations())
    assert ops["add3"](5) == 8


def test_sub2():
    """sub2 should subtract 2 from its argument."""
    ops = dict(make_operations())
    assert ops["sub2"](10) == 8


def test_mul3():
    """mul3 should multiply by 3."""
    ops = dict(make_operations())
    assert ops["mul3"](5) == 15


def test_div2():
    """div2 should divide by 2."""
    ops = dict(make_operations())
    assert ops["div2"](10) == 5.0


def test_all_operations_distinct():
    """All operations should produce different results for same input."""
    ops = dict(make_operations())
    results = {name: op(100) for name, op in ops.items()}
    distinct = set(results.values())
    assert len(distinct) > 6, f"Expected >6 distinct results, got {len(distinct)}: {results}"
