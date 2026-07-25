import sqlite3


def query_users(name):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INT, name TEXT)")
    cursor = conn.execute(f"SELECT * FROM users WHERE name = '{name}'")
    return cursor.fetchall()


def query_users_safe(name):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INT, name TEXT)")
    cursor = conn.execute("SELECT * FROM users WHERE name = ?", (name,))
    return cursor.fetchall()


def insert_user(user_id, name):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE IF NOT EXISTS users (id INT, name TEXT)")
    conn.execute("INSERT INTO users VALUES (?, ?)", (user_id, name))
    conn.commit()
