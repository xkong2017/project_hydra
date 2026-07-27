import pytest
from source import TodoList

@pytest.fixture
def todo_list():
    return TodoList()

def test_create_todo_initializes_correctly(todo_list):
    todo = todo_list.create("Buy groceries")
    assert todo["id"] == 1
    assert todo["title"] == "Buy groceries"
    assert todo["completed"] is False

def test_list_returns_empty_list_initially(todo_list):
    assert todo_list.list() == []

def test_list_returns_all_created_todos(todo_list):
    todo_list.create("Task 1")
    todo_list.create("Task 2")
    todos = todo_list.list()
    assert len(todos) == 2
    assert todos[0]["title"] == "Task 1"
    assert todos[1]["title"] == "Task 2"

def test_complete_marks_todo_as_done(todo_list):
    todo = todo_list.create("Read book")
    result = todo_list.complete(todo["id"])
    assert result["completed"] is True
    assert result["id"] == todo["id"]

def test_complete_nonexistent_todo_raises_error(todo_list):
    with pytest.raises(ValueError):
        todo_list.complete(999)

def test_delete_removes_todo_from_list(todo_list):
    todo_list.create("Task A")
    todo_list.create("Task B")
    todo_list.delete(1)
    assert len(todo_list.list()) == 1
    assert todo_list.list()[0]["title"] == "Task B"

def test_delete_nonexistent_todo_raises_error(todo_list):
    with pytest.raises(ValueError):
        todo_list.delete(999)

def test_complete_reflects_in_list(todo_list):
    todo_list.create("Write docs")
    todo_list.complete(1)
    assert todo_list.list()[0]["completed"] is True

def test_delete_reflects_in_list(todo_list):
    todo_list.create("Task X")
    todo_list.delete(1)
    assert todo_list.list() == []

def test_create_multiple_todos_assigns_increasing_ids(todo_list):
    t1 = todo_list.create("First")
    t2 = todo_list.create("Second")
    assert t1["id"] == 1
    assert t2["id"] == 2