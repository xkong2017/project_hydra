from auth import Authenticator, AccessController


class API:
    def __init__(self):
        self._auth = Authenticator()
        self._access = AccessController()

    def register_user_token(self, user_id, token):
        self._auth.register_token(user_id, token)

    def grant_access(self, user_id, resource):
        self._access.grant(user_id, resource)

    def request(self, token, resource):
        identity = self._auth.authenticate(token)
        if identity is None:
            return {"status": "error", "reason": "invalid_token"}

        user_id = identity["user_id"]
        if self._access.check(user_id, resource):
            return {"status": "ok", "user": user_id}

        return {"status": "error", "reason": "access_denied"}
