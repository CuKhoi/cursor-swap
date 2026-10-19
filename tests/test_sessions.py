import base64
import json
from pathlib import Path
import sqlite3

import pytest

from cursorswap import cli, cli_session, ide, usage
from cursorswap.store import Error, Store, atomic_write, metadata, private_dir, read_json, write_json


def jwt(sub, revision=1):
    payload = base64.urlsafe_b64encode(json.dumps({"sub": sub, "rev": revision}).encode()).decode().rstrip("=")
    return f"header.{payload}.signature"


def database(email="a@example.com", token=None, extra=None):
    rows = {"cursorAuth/accessToken": token or jwt("auth0|a"),
            "cursorAuth/refreshToken": token or jwt("auth0|a"), "cursorAuth/cachedEmail": email}
    rows.update(extra or {})
    with sqlite3.connect(ide.db_path()) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value TEXT)")
        conn.execute("DELETE FROM ItemTable")
        conn.executemany("INSERT INTO ItemTable VALUES (?, ?)", rows.items())
    return rows


def set_cli(isolated, email, access, refresh="refresh"):
    isolated["secrets"].update({"cursor-access-token": access, "cursor-refresh-token": refresh})
    private_dir(cli_session.config_path().parent)
    write_json(cli_session.config_path(), {"authInfo": {"email": email, "authId": "auth0|" + email[0]},
               "autoReviewAvailabilityCache": {"account": email}, "serverConfigCache": {"account": email},
               "theme": "dark"})


@pytest.mark.parametrize("value", ["", "broken", "a.!.c", "a.W10.c", "a.bnVsbA.c", None, "a.eyJzdWIiOjF9.c"])
def test_bad_jwt(value):
    assert ide.jwt_sub(value) == ""


@pytest.mark.parametrize("sub", ["auth0|a", "quote'and_underscore", "người-dùng", "x" * 7])
def test_jwt(sub):
    assert ide.jwt_sub(jwt(sub)) == sub


def test_ide_save_back_restore_and_permissions(isolated):
    old = jwt("auth0|a")
    database(token=old)
    assert cli.main(["ide-add", "a", "--alias", "first"]) == 0
    database("b@example.com", jwt("auth0|b"))
    assert cli.main(["ide-add", "b"]) == 0
    rotated = jwt("auth0|a", 2)
    database(token=rotated, extra={"cursorAuth/cachedTeam": "stale", "cursorAuth/teamId": "old-team",
             **dict.fromkeys(ide.BYOK_KEYS, "user's-provider-key"), "unrelated": "keep"})
    isolated["running"] = True
    assert cli.main(["ide-use", "b"]) == 0
    store = Store()
    saved = read_json(store.require("first") / "ide-auth.json")
    assert ide.row_value(saved, "accessToken") == rotated
    assert ide.row_value(saved, "cachedTeam") == "stale"
    with sqlite3.connect(ide.db_path()) as conn:
        rows = dict(conn.execute("SELECT key, value FROM ItemTable"))
    assert rows["cursorAuth/accessToken"] == jwt("auth0|b")
    assert "cursorAuth/cachedTeam" not in rows
    assert "cursorAuth/teamId" not in rows
    assert all(rows[key] == "user's-provider-key" for key in ide.BYOK_KEYS)
    assert rows["unrelated"] == "keep"
    assert ["osascript", "-e", 'quit app "Cursor"'] in isolated["calls"]
    assert ["open", "-a", "Cursor"] in isolated["calls"]
    assert not any(call[0] in ("security", "agent") for call in isolated["calls"])
    for directory in store.profiles():
        assert directory.stat().st_mode & 0o777 == 0o700
        assert all(f.stat().st_mode & 0o777 == 0o600 for f in directory.iterdir())


def test_ide_metadata_and_email_fallback(isolated):
    set_cli(isolated, "a@example.com", jwt("auth0|a"))
    assert cli.main(["add", "a", "--alias", "original"]) == 0
    directory = Store().require("a")
    before = read_json(directory / "meta.json")
    database(email="", token=jwt("auth0|a"))
    assert ide.current_email(Store()) == "a@example.com"
    assert cli.main(["ide-add", "a", "--alias", "ignored"]) == 0
    assert read_json(directory / "meta.json") == {**before, "ide_email": "a@example.com"}
    database("b@example.com", jwt("auth0|b"))
    assert cli.main(["ide-add", "b", "--alias", "new"]) == 0
    assert read_json(Store().require("b") / "meta.json")["alias"] == "new"


def test_ide_errors_and_no_real_subprocess(isolated, capsys, monkeypatch):
    assert cli.main(["ide-add", "a"]) == 1
    assert "not found" in capsys.readouterr().err
    database(email="", token=jwt("unknown"))
    assert cli.main(["ide-add", "a"]) == 1
    assert "cached email" in capsys.readouterr().err
    database()
    assert cli.main(["ide-add", "a"]) == 0
    isolated.update(running=True, stuck=True)
    sleeps = []
    monkeypatch.setattr(ide.time, "sleep", sleeps.append)
    assert cli.main(["ide-switch", "a"]) == 1
    assert "didn't quit in time" in capsys.readouterr().err
    assert sleeps == [1] * 15
    assert not any(call[0] == "open" for call in isolated["calls"])


def test_ide_restore_rolls_back_on_insert_failure():
    database()
    assert cli.main(["ide-add", "a"]) == 0
    directory = Store().require("a")
    write_json(directory / "ide-auth.json", [
        {"key": "cursorAuth/accessToken", "value": "new"}, {"key": "fail", "value": "fail"}])
    with sqlite3.connect(ide.db_path()) as conn:
        conn.execute("CREATE TRIGGER reject BEFORE INSERT ON ItemTable WHEN NEW.key='fail' BEGIN SELECT RAISE(ABORT, 'test'); END")
    before = ide.live_rows()
    with pytest.raises(Error, match="couldn't write"):
        ide.restore(directory)
    assert ide.live_rows() == before


def test_ide_locked_retry_limit(monkeypatch):
    database()
    assert cli.main(["ide-add", "a"]) == 0
    directory = Store().require("a")
    sleeps = []
    monkeypatch.setattr(ide.time, "sleep", sleeps.append)
    with sqlite3.connect(ide.db_path()) as locked:
        locked.execute("BEGIN IMMEDIATE")
        with pytest.raises(Error, match="couldn't write"):
            ide.restore(directory)
    assert sleeps == [1] * 4
    # Retry succeeds when a helper releases its lock.
    with sqlite3.connect(ide.db_path()) as locked:
        locked.execute("BEGIN IMMEDIATE")
        monkeypatch.setattr(ide.time, "sleep", lambda _: locked.rollback())
        ide.restore(directory)


def test_ide_relative_db_and_corrupt_db(monkeypatch):
    database()
    monkeypatch.setenv("CURSOR_SWAP_IDE_DB", "state.vscdb")
    assert ide.live_token()
    ide.db_path().write_text("not sqlite")
    assert ide.live_rows() == []


def test_add_both_cli_and_ide(isolated):
    set_cli(isolated, "a@example.com", "cli-token")
    database("ide@example.com")
    assert cli.main(["add", "both", "--alias", "b"]) == 0
    directory = Store().require("b")
    meta = read_json(directory / "meta.json")
    assert meta["type"] == "session"
    assert meta["email"] == "a@example.com"
    assert meta["ide_email"] == "ide@example.com"
    assert (directory / "access-token").read_text() == "cli-token"
    assert (directory / "ide-auth.json").is_file()
    assert all(f.stat().st_mode & 0o777 == 0o600 for f in directory.iterdir())


def test_add_neither_or_ide_only(capsys):
    assert cli.main(["add", "empty"]) == 1
    assert "not logged in anywhere" in capsys.readouterr().err
    database()
    assert cli.main(["add", "only"]) == 0
    assert read_json(Store().require("only") / "meta.json")["type"] == "ide-only"
    assert cli.main(["run", "only"]) == 1
    assert "only has an IDE session" in capsys.readouterr().err


def test_cli_login_restore_and_stale_cache(isolated, monkeypatch):
    set_cli(isolated, "a@example.com", "a-access", "a-refresh")
    assert cli.main(["login", "a"]) == 0
    assert isolated["calls"][:2] == [["agent", "logout"], ["agent", "login"]]
    set_cli(isolated, "b@example.com", "b-access", "b-refresh")
    monkeypatch.setattr(usage, "summary", lambda token: ("network unavailable", False))
    assert cli.main(["switch", "a"]) == 0
    assert cli_session.current_email() == "a@example.com"
    assert isolated["secrets"]["cursor-access-token"] == "a-access"
    assert isolated["secrets"]["cursor-refresh-token"] == "a-refresh"
    config = read_json(cli_session.config_path())
    assert config["theme"] == "dark"
    assert config["serverConfigCache"] == {"account": "a@example.com"}
    assert cli_session.config_path().stat().st_mode & 0o777 == 0o600
    isolated["calls"].clear()
    assert cli.main(["use", "a"]) == 0
    assert not any(c[0] == "security" and c[1] == "add-generic-password" for c in isolated["calls"])
    isolated["secrets"].clear()
    assert cli.main(["use", "a"]) == 0
    assert isolated["secrets"]["cursor-access-token"] == "a-access"


def test_rotation_prefers_cli_then_ide_and_skips_disabled(isolated, monkeypatch):
    set_cli(isolated, "a@example.com", "a-token")
    assert cli.main(["add", "a"]) == 0
    database("b@example.com", jwt("auth0|b"))
    assert cli.main(["ide-add", "b"]) == 0
    database("c@example.com", jwt("auth0|c"))
    assert cli.main(["ide-add", "c"]) == 0
    assert cli.main(["disable", "c"]) == 0
    assert cli.main(["add-token", "key"]) == 0
    chosen = []
    monkeypatch.setattr(cli.CLI, "switch_profile", lambda self, directory: chosen.append(directory.name))
    assert cli.main(["switch"]) == 0
    assert chosen[-1] == "b"
    isolated["secrets"].clear()
    database("b@example.com", jwt("auth0|b"))
    assert cli.main(["switch"]) == 0
    assert chosen[-1] == "a"
    assert cli.main(["disable", "a"]) == 0
    assert cli.main(["disable", "b"]) == 0
    assert cli.main(["switch"]) == 1


def test_run_restores_previous_on_failure(isolated):
    set_cli(isolated, "a@example.com", "a-access")
    assert cli.main(["add", "a"]) == 0
    set_cli(isolated, "b@example.com", "b-access")
    assert cli.main(["add", "b"]) == 0
    isolated["agent_status"] = 7
    assert cli.main(["run", "a", "--", "create-chat"]) == 7
    assert isolated["secrets"]["cursor-access-token"] == "b-access"
    assert cli_session.current_email() == "b@example.com"
    assert ["agent", "create-chat"] in isolated["calls"]
    assert not any(c[0] in ("pgrep", "osascript", "open") for c in isolated["calls"])


def test_run_api_key_mapped_exec(isolated):
    assert cli.main(["add-token", "sk-key", "--alias", "key"]) == 0
    assert cli.main(["map", "key"]) == 0
    with pytest.raises(SystemExit) as exc:
        cli.main(["run", "--", "create-chat"])
    assert exc.value.code == 0
    assert isolated["calls"] == [["agent", "--api-key", "sk-key", "create-chat"]]
    assert cli.main(["switch", "key"]) == 1


def test_status_alias(isolated):
    assert cli.main(["current"]) == 0
    assert isolated["calls"] == [["agent", "status"], ["agent", "about"]]


def test_effective_tokens_prefer_live_then_snapshot(isolated):
    set_cli(isolated, "a@example.com", "saved-cli")
    database("ide@example.com", jwt("auth0|ide"))
    assert cli.main(["add", "a"]) == 0
    directory = Store().require("a")
    isolated["secrets"]["cursor-access-token"] = "rotated-cli"
    assert usage.effective_access_token(Store(), directory) == "rotated-cli"
    isolated["secrets"].clear()
    database("ide@example.com", jwt("auth0|ide", 2))
    assert usage.effective_access_token(Store(), directory) == jwt("auth0|ide", 2)
    database("other@example.com", jwt("other"))
    assert usage.effective_access_token(Store(), directory) == "saved-cli"
    (directory / "access-token").unlink()
    assert usage.effective_access_token(Store(), directory) == jwt("auth0|ide")
