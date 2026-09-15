storage = None


def set_storage(db):
    global storage  # noqa: PLW0603
    storage = db


def get_storage():
    return storage
