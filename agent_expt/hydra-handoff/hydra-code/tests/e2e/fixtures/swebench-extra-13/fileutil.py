import os

BASE_DIR = "/data/files"


def read_file(filename):
    path = os.path.join(BASE_DIR, filename)
    if not os.path.exists(path):
        return None
    with open(path) as f:
        return f.read()


def list_files():
    return os.listdir(BASE_DIR)


def file_exists(filename):
    path = os.path.join(BASE_DIR, filename)
    return os.path.exists(path)
