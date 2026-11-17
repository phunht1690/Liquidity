import sqlite3
import pytest
from src.data.sqlite_connection import sqlite_session


def test_commit_and_read_only_connections_are_closed(tmp_path):
    path = tmp_path/'cache.sqlite3'
    with sqlite_session(path) as db:
        db.execute('CREATE TABLE samples(value INTEGER)')
        db.execute('INSERT INTO samples VALUES(7)')
    with pytest.raises(sqlite3.ProgrammingError): db.execute('SELECT 1')
    with sqlite_session(path.as_uri()+'?mode=ro', uri=True) as read:
        assert read.execute('SELECT value FROM samples').fetchone() == (7,)
    with pytest.raises(sqlite3.ProgrammingError): read.execute('SELECT 1')


def test_failure_rolls_back_without_leaking_connection(tmp_path):
    path = tmp_path/'cache.sqlite3'
    with sqlite_session(path) as db: db.execute('CREATE TABLE samples(value INTEGER)')
    with pytest.raises(RuntimeError):
        with sqlite_session(path) as failed:
            failed.execute('INSERT INTO samples VALUES(9)')
            raise RuntimeError('abort transaction')
    with pytest.raises(sqlite3.ProgrammingError): failed.execute('SELECT 1')
    with sqlite_session(path) as db:
        assert db.execute('SELECT COUNT(*) FROM samples').fetchone()[0] == 0
