"""Cursor.app's sqlite-stored session and the quit/restore/relaunch sequence."""
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
from contextlib import closing

from .i18n import t
from .store import Error, label, metadata, private_dir, read_json, write_json

BYOK_KEYS = tuple("cursorAuth/" + name for name in (
    "openAIKey", "claudeKey", "googleKey", "azureApiKey", "bedrockAccessKey", "bedrockSecretKey"))


def command(args, quiet=False, check=False):
    result = subprocess.run(args, stdout=subprocess.DEVNULL if quiet else None,
                            stderr=subprocess.DEVNULL if quiet else None)
    if check and result.returncode:
        raise Error(f"{args[0]} exited with status {result.returncode}")
    return result.returncode


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


def snapshot_rows(directory):
    path = directory / "ide-auth.json"
    try:
        return read_json(path) if path.is_file() else []
    except (OSError, ValueError):
        return []


def snapshot_sub(directory):
    return jwt_sub(row_value(snapshot_rows(directory), "accessToken"))


def profile_for_sub(store, sub):
    """The saved profile holding the same Cursor account (JWT sub) - survives token
    rotation and a lagging/missing cachedEmail, unlike matching by email."""
    if not sub:
        return None
    return next((d for d in store.profiles() if snapshot_sub(d) == sub), None)


def active_profile(store):
    return profile_for_sub(store, jwt_sub(live_token()))


def email_for_rows(store, rows):
    email = row_value(rows, "cachedEmail")
    if email:
        return email
    # cachedEmail can lag behind a fresh login - fall back to a saved profile
    # of the same account.
    directory = profile_for_sub(store, jwt_sub(row_value(rows, "accessToken")))
    return read_json(directory / "meta.json").get("email", "") if directory else ""


def current_email(store):
    return email_for_rows(store, live_rows())


def capture(store, name, alias, confirm):
    store.ensure()
    if not db_path().is_file():
        raise Error(t("err_ide_db_not_found", db_path()))
    rows = live_rows()
    if not row_value(rows, "accessToken"):
        raise Error(t("err_no_ide_rows"))
    email = email_for_rows(store, rows)
    if not email:
        raise Error(t("err_no_cached_email"))
    directory = store.named(name)
    if directory.is_dir():
        meta = read_json(directory / "meta.json")
        old = meta.get("ide_email") or meta.get("email")
        if old != email:
            confirm(t("confirm_overwrite", name, old or "?"))
        meta.update(email=email, ide_email=email, type="ide-only", saved_at=metadata(email, 0, "", "")["saved_at"])
        alias = alias or meta.get("alias")
        meta["alias"] = alias or None
    else:
        meta = metadata(email, store.next_slot(), alias, "ide-only")
        meta["ide_email"] = email
    private_dir(directory)
    write_json(directory / "ide-auth.json", rows)
    write_json(directory / "meta.json", meta)
    print(t("msg_saved_ide", name, email, meta["slot"]))


def save_back(store):
    rows = live_rows()
    directory = profile_for_sub(store, jwt_sub(row_value(rows, "accessToken")))
    if directory:
        write_json(directory / "ide-auth.json", rows)


def restore(directory):
    if not (directory / "ide-auth.json").is_file():
        raise Error(t("err_no_ide_captured", label(directory)))
    replace_auth_rows(read_json(directory / "ide-auth.json"))


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


def quit_app():
    """Quits Cursor.app if it's running (no prompt - switching is the whole point, and
    the app is relaunched right after); returns whether it was running."""
    if not running():
        return False
    print(t("msg_ide_quitting"))
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
    if not (directory / "ide-auth.json").is_file():
        raise Error(t("err_no_ide_captured_ref", label(directory), directory.name))
    was_running = quit_app()
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
    if not profile_for_sub(store, jwt_sub(row_value(rows, "accessToken"))):
        confirm(t("confirm_ide_logout_unsaved", email_for_rows(store, rows) or "?"))
    was_running = quit_app()
    save_back(store)
    replace_auth_rows([])
    print(t("msg_ide_logged_out_local"))
    relaunch(was_running)
