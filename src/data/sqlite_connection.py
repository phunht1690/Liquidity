"""Short-lived SQLite transactions that always release their native resources."""
from contextlib import contextmanager
import sqlite3


@contextmanager
def sqlite_session(*args, **kwargs):
    # Connection.__exit__ commits/rolls back; it does not close the connection.
    connection = sqlite3.connect(*args, **kwargs)
    try:
        with connection:
            yield connection
    finally:
        connection.close()
