from access import can_access, can_edit, can_delete


def test_admin_can_anything():
    user = {"role": "admin", "id": 1, "permissions": []}
    resource = {"owner": 2, "public": False}
    assert can_access(user, resource, "read")
    assert can_access(user, resource, "write")


def test_owner_with_permission():
    user = {"role": "user", "id": 1, "permissions": ["write"]}
    resource = {"owner": 1, "public": False}
    assert can_edit(user, resource)


def test_owner_without_permission():
    user = {"role": "user", "id": 1, "permissions": []}
    resource = {"owner": 1, "public": False}
    assert not can_edit(user, resource), "Owner without write permission should not edit"


def test_non_owner_with_permission():
    user = {"role": "user", "id": 2, "permissions": ["write"]}
    resource = {"owner": 1, "public": False}
    assert not can_edit(user, resource), "Non-owner should not edit even with permission"


def test_public_read():
    user = {"role": "user", "id": 2, "permissions": []}
    resource = {"owner": 1, "public": True}
    assert can_access(user, resource, "read")


def test_public_write_denied():
    user = {"role": "user", "id": 2, "permissions": []}
    resource = {"owner": 1, "public": True}
    assert not can_access(user, resource, "write")
