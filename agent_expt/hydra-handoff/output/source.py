class TodoList:
    def __init__(self):
        self.todos = []
        self.next_id = 1

    def create(self, title):
        todo = {"id": self.next_id, "title": title, "completed": False}
        self.todos.append(todo)
        self.next_id += 1
        return todo

    def list(self):
        return self.todos

    def complete(self, todo_id):
        for todo in self.todos:
            if todo["id"] == todo_id:
                todo["completed"] = True
                return todo
        raise ValueError("Todo not found")

    def delete(self, todo_id):
        for i, todo in enumerate(self.todos):
            if todo["id"] == todo_id:
                self.todos.pop(i)
                return
        raise ValueError("Todo not found")