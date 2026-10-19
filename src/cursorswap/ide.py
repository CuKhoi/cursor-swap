"""Cursor.app's independent sqlite session and quit/restore/relaunch sequence."""
import base64
import json
import os
from pathlib import Path
import sqlite3
import time
from contextlib import closing

from .cli_session import command
from .i18n import t
from .store import Error, label, metadata, private_dir, read_json, write_json

BYOK_KEYS = tuple("cursorAuth/" + name for name in (
    "openAIKey", "claudeKey", "googleKey", "azureApiKey", "bedrockAccessKey", "bedrockSecretKey"))


def db_path():
    return Path(os.environ.get("CURSOR_SWAP_IDE_DB") or
                Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb")


def jwt_sub(token):
    try:
        payload = token.split(".")[1]
        value = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        sub = value.get("sub", "")
        return sub if isinstance(sub, str) else ""
    except (ValueError, IndexError, TypeError, AttributeError):
        return ""


def live_rows():
    if not db_path().is_file():
        return []
    try:
        with closing(sqlite3.connect(db_path().resolve().as_uri() + "?mode=ro", uri=True, timeout=0)) as conn:
            return [{"key": key, "value": value} for key, value in conn.execute(
                "SELECT key, value FROM ItemTable WHERE key LIKE ?", ("cursorAuth/%",))]
    except sqlite3.Error:
        return []


def row_value(rows, key):
    return next((r["value"] for r in rows if r["key"] == "cursorAuth/" + key), "")


def live_token():
    return row_value(live_rows(), "accessToken")


def email_for_rows(store, rows):
    email = row_value(rows, "cachedEmail")
    if email:
        return email
    sub = jwt_sub(row_value(rows, "accessToken"))
    if sub:
        for directory in store.profiles():
            try:
                auth = read_json(directory / "cli-config.json").get("authInfo", {})
                if auth.get("authId") == sub:
                    return auth.get("email") or ""
            except (OSError, ValueError, AttributeError):
                continue
    return ""


def current_email(store):
    return email_for_rows(store, live_rows())


def capture(store, name, alias=""):
    store.ensure()
    if not db_path().is_file():
        raise Error(t("err_ide_db_not_found", db_path()))
    rows = live_rows()
    if not rows:
        raise Error(t("err_no_ide_rows"))
    email = email_for_rows(store, rows)
    if not email:
        raise Error(t("err_no_cached_email"))
    directory = store.named(name)
    if directory.is_dir():
        meta = read_json(directory / "meta.json")
        slot = meta["slot"]
        # Existing profiles keep all metadata, including alias and saved_at.
        meta["ide_email"] = email
    else:
        slot = store.next_slot()
        meta = metadata(email, slot, alias, "ide-only")
        meta["ide_email"] = email
    private_dir(directory)
    write_json(directory / "ide-auth.json", rows)
    write_json(directory / "meta.json", meta)
    print(t("msg_saved_ide", name, email, slot))


def save_back(store):
    rows = live_rows()
    sub = jwt_sub(row_value(rows, "accessToken"))
    if not sub:
        return
    for directory in store.profiles():
        path = directory / "ide-auth.json"
        if path.is_file() and jwt_sub(row_value(read_json(path), "accessToken")) == sub:
            write_json(path, rows)
            return


def restore(directory):
    snapshot = directory / "ide-auth.json"
    if not snapshot.is_file():
        raise Error(t("err_no_ide_captured", label(directory)))
    replace_auth_rows(read_json(snapshot))


def replace_auth_rows(rows):
    for attempt in range(5):
        try:
            with closing(sqlite3.connect(db_path(), timeout=0)) as conn:
                with conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("DELETE FROM ItemTable WHERE key LIKE ? AND key NOT IN (?, ?, ?, ?, ?, ?)",
                                 ("cursorAuth/%", *BYOK_KEYS))
                    conn.executemany("INSERT OR REPLACE INTO ItemTable(key,value) VALUES (?, ?)",
                                     [(row["key"], row["value"] if isinstance(row["value"], str)
                                       else json.dumps(row["value"], ensure_ascii=False, separators=(",", ":")))
                                      for row in rows])
            return
        except sqlite3.Error as exc:
            if "database is locked" not in str(exc).lower() or attempt == 4:
                raise Error(t("err_ide_write_failed", db_path())) from exc
            time.sleep(1)


def running():
    return command(["pgrep", "-x", "Cursor"], quiet=True) == 0


def quit_app(confirm):
    """Quits Cursor.app (after confirming) if it's running; returns whether it was."""
    if not running():
        return False
    confirm(t("confirm_ide_quit"))
    command(["osascript", "-e", 'quit app "Cursor"'], quiet=True)
    waited = 0
    while running() and waited < 15:
        time.sleep(1)
        waited += 1
    if running():
        raise Error(t("err_ide_quit_timeout"))
    return True


def relaunch(was_running):
    if was_running:
        command(["open", "-a", "Cursor"], check=True)
        print(t("msg_relaunched"))
    else:
        print(t("msg_ide_not_running"))


def switch(store, directory, confirm):
    if not db_path().is_file():
        raise Error(t("err_ide_db_not_found", db_path()))
    was_running = quit_app(confirm)
    save_back(store)
    restore(directory)
    print(t("msg_swapped_ide", label(directory)))
    relaunch(was_running)


def logout_local(store, confirm):
    """Signs the IDE out on this machine only, by deleting its auth rows. Unlike the
    IDE's own "Log out" (POST /auth/logout), the session stays valid server-side, so
    its saved snapshot keeps working - the way to log in a second account."""
    if not db_path().is_file():
        raise Error(t("err_ide_db_not_found", db_path()))
    rows = live_rows()
    if not row_value(rows, "accessToken"):
        print(t("msg_ide_already_logged_out"))
        return
    sub = jwt_sub(row_value(rows, "accessToken"))
    saved = sub and any(
        (d / "ide-auth.json").is_file() and jwt_sub(row_value(read_json(d / "ide-auth.json"), "accessToken")) == sub
        for d in store.profiles())
    if not saved:
        confirm(t("confirm_ide_logout_unsaved", email_for_rows(store, rows) or "?"))
    was_running = quit_app(confirm)
    save_back(store)
    replace_auth_rows([])
    print(t("msg_ide_logged_out_local"))
    relaunch(was_running)
