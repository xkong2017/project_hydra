def can_access(user, resource, action):
    is_admin = user.get("role") == "admin"
    is_owner = resource.get("owner") == user.get("id")
    is_public = resource.get("public", False)
    permissions = user.get("permissions", [])

    if (is_admin or is_owner) and action in permissions:
        return True
    if is_public and action == "read":
        return True
    return False


def can_edit(user, resource):
    return can_access(user, resource, "write")


def can_delete(user, resource):
    return can_access(user, resource, "delete")
