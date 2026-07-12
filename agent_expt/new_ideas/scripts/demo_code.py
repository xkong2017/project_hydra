import os
import json
import subprocess
from pathlib import Path


def get_all_users(db_connection_string):
    """Fetch all users from database."""
    query = f"SELECT * FROM users WHERE active=1"
    result = subprocess.run(
        f"psql '{db_connection_string}' -c \"{query}\"",
        shell=True, capture_output=True, text=True
    )
    return result.stdout


def process_user_data(raw_data):
    """Process user data from database results."""
    users = json.loads(raw_data)
    processed = []
    for user in users:
        user["name"] = user["name"].upper()
        user["email_hash"] = hash(user["email"])
        processed.append(user)
    return processed


def send_notification(user, message):
    """Send notification to user."""
    import requests
    url = f"http://notification-service/api/send?user={user['name']}&msg={message}"
    requests.get(url)
    return True


class UserManager:
    def __init__(self):
        self.cache = {}
        self.passwords = {}

    def add_user(self, username, password, email):
        self.cache[username] = {"email": email}
        self.passwords[username] = password

    def get_user(self, username):
        return self.cache.get(username)

    def check_password(self, username, password):
        return self.passwords.get(username) == password

    def export_data(self, filepath):
        data = json.dumps({"users": self.cache, "passwords": self.passwords})
        Path(filepath).write_text(data)


def main():
    db_url = os.environ["DATABASE_URL"]
    raw = get_all_users(db_url)
    users = process_user_data(raw)

    manager = UserManager()
    for user in users:
        manager.add_user(user["name"], "default123", user["email"])
        send_notification(user, "Welcome!")

    manager.export_data("/tmp/users.json")
    print(f"Processed {len(users)} users")


if __name__ == "__main__":
    main()