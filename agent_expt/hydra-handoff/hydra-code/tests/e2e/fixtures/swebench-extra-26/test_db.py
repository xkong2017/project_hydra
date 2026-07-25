import pytest
from db import insert_user, query_users_safe


def test_insert_and_query():
    insert_user(1, "alice")
    result = query_users_safe("alice")
    assert len(result) > 0


def test_sql_injection_prevented():
    insert_user(1, "alice")
    result = query_users_safe("' OR '1'='1")
    assert len(result) == 0, "SQL injection should not return all rows!"
