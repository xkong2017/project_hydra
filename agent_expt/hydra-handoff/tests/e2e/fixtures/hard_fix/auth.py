class Authenticator:
    def __init__(self):
        self._tokens = {}

    def register_token(self, user_id, token):
        self._tokens[token] = user_id

    def authenticate(self, token):
        if not token:
            return {"user_id": "guest", "role": "guest"}
        if token in self._tokens:
            return {"user_id": self._tokens[token], "role": "user"}
        return None


class AccessController:
    def __init__(self):
        self._permissions = {}

    def grant(self, user_id, resource):
        if user_id not in self._permissions:
            self._permissions[user_id] = set()
        self._permissions[user_id].add(resource)

    def check(self, user_id, resource):
        if user_id not in self._permissions:
            return False
        return resource in self._permissions[user_id]
