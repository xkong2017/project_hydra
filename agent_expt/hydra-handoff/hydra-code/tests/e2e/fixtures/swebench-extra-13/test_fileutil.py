from fileutil import read_file, file_exists


def test_read_existing():
    result = read_file("test.txt")
    assert result is not None


def test_path_traversal_blocked():
    result = read_file("../../../etc/passwd")
    assert result is None, "Path traversal should be blocked!"


def test_file_exists_normal():
    assert file_exists("test.txt") is True


def test_file_exists_traversal():
    assert file_exists("../../../etc") is False, "Path traversal should not exist in sandbox!"
