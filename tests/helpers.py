"""Fake Cursor.app sessions: JWTs and the IDE's sqlite ItemTable."""
import base64
import json
import sqlite3

from cursorswap import cli, ide


def jwt(sub, revision=1):
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub, "rev": revision}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def database(email="a@example.com", token=None, extra=None):
    """Replaces the fake IDE db with one logged into `email` (sub auth0|<first letter>)."""
    token = token or jwt("auth0|" + (email or "x")[0])
    rows = {"cursorAuth/accessToken": token, "cursorAuth/refreshToken": token, "cursorAuth/cachedEmail": email}
    rows.update(extra or {})
    with sqlite3.connect(ide.db_path()) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value TEXT)")
        conn.execute("DELETE FROM ItemTable")
        conn.executemany("INSERT INTO ItemTable VALUES (?, ?)", rows.items())
    return rows


def ide_rows():
    with sqlite3.connect(ide.db_path()) as conn:
        return dict(conn.execute("SELECT key, value FROM ItemTable"))


def add(name, email, *extra):
    """Logs the fake IDE into `email` and saves it as profile `name`."""
    database(email)
    assert cli.main(["add", name, *extra]) == 0
