import pytest

from cursorswap import cli, ide, usage
from cursorswap.store import Error, Store, read_json, write_json

from helpers import add, database, ide_rows, jwt


@pytest.mark.parametrize("value", ["", "broken", "a.!.c", "a.W10.c", "a.bnVsbA.c", None, "a.eyJzdWIiOjF9.c"])
def test_bad_jwt(value):
    assert ide.jwt_sub(value) == ""


@pytest.mark.parametrize("sub", ["auth0|a", "quote'and_underscore", "người-dùng", "x" * 7])
def test_jwt(sub):
    assert ide.jwt_sub(jwt(sub)) == sub


def test_switch_saves_back_rotated_token_and_clears_stale_rows(isolated):
    add("a", "a@example.com", "--alias", "first")
    add("b", "b@example.com")
    rotated = jwt("auth0|a", 2)
    database(token=rotated, extra={"cursorAuth/cachedTeam": "stale", "cursorAuth/teamId": "old-team",
             **dict.fromkeys(ide.BYOK_KEYS, "user's-provider-key"), "unrelated": "keep"})
    isolated["running"] = True
    assert cli.main(["switch", "b"]) == 0
    store = Store()
    saved = read_json(store.require("first") / "ide-auth.json")
    assert ide.row_value(saved, "accessToken") == rotated
    assert ide.row_value(saved, "cachedTeam") == "stale"
    rows = ide_rows()
    assert rows["cursorAuth/accessToken"] == jwt("auth0|b")
    assert "cursorAuth/cachedTeam" not in rows and "cursorAuth/teamId" not in rows
    assert all(rows[key] == "user's-provider-key" for key in ide.BYOK_KEYS)
    assert rows["unrelated"] == "keep"
    assert ["osascript", "-e", 'quit app "Cursor"'] in isolated["calls"]
    assert ["open", "-a", "Cursor"] in isolated["calls"]
    assert not any(call[0] in ("security", "agent") for call in isolated["calls"])
    for directory in store.profiles():
        assert directory.stat().st_mode & 0o777 == 0o700
        assert all(f.stat().st_mode & 0o777 == 0o600 for f in directory.iterdir())


@pytest.mark.parametrize("command", ["switch", "use", "ide-switch", "ide-use"])
def test_switch_aliases_and_already_active(isolated, command, capsys):
    add("a", "a@example.com")
    add("b", "b@example.com")
    assert cli.main([command, "a"]) == 0
    assert ide_rows()["cursorAuth/accessToken"] == jwt("auth0|a")
    isolated["calls"].clear()
    assert cli.main([command, "a"]) == 0
    assert "Already on" in capsys.readouterr().out
    assert not isolated["calls"]


def test_rotation_by_account_skips_disabled_and_legacy(isolated):
    add("a", "a@example.com")
    add("b", "b@example.com")
    add("c", "c@example.com")
    legacy = Store().named("legacy")
    legacy.mkdir()
    write_json(legacy / "meta.json", {"email": "l@x", "slot": 9, "type": "session", "enabled": True,
                                      "alias": None, "saved_at": "x"})
    assert cli.main(["disable", "b"]) == 0
    # Matched by JWT sub even with no cachedEmail.
    database(email="", token=jwt("auth0|a", 3))
    assert cli.main(["switch"]) == 0
    assert ide_rows()["cursorAuth/cachedEmail"] == "c@example.com"
    assert cli.main(["switch"]) == 0
    assert ide_rows()["cursorAuth/cachedEmail"] == ""  # back to a's saved-back rows
    assert ide.jwt_sub(ide_rows()["cursorAuth/accessToken"]) == "auth0|a"
    with pytest.raises(Error, match="no captured IDE session"):
        ide.switch(Store(), legacy, lambda m: None)


def test_switch_with_nothing_saved():
    assert cli.main(["switch"]) == 1


def test_add_overwrite_confirms_on_account_change(isolated, monkeypatch):
    add("a", "a@example.com", "--alias", "short")
    directory = Store().require("a")
    before = read_json(directory / "meta.json")
    database("a@example.com", jwt("auth0|a", 2))
    assert cli.main(["ide-add", "a"]) == 0  # same account: refresh silently, keep alias/slot
    assert read_json(directory / "meta.json") == before
    database("b@example.com")
    monkeypatch.delenv("CURSOR_SWAP_YES")
    with pytest.raises(SystemExit):
        cli.main(["add", "a"])
    assert read_json(directory / "meta.json")["email"] == "a@example.com"


def test_add_email_fallback_and_errors(isolated, capsys):
    assert cli.main(["add", "a"]) == 1
    assert "not found" in capsys.readouterr().err
    database(email="", token=jwt("unknown"))
    assert cli.main(["add", "a"]) == 1
    assert "cached email" in capsys.readouterr().err
    add("a", "a@example.com")
    database(email="", token=jwt("auth0|a", 2))
    assert ide.current_email(Store()) == "a@example.com"
    assert cli.main(["add", "a"]) == 0


def test_quit_timeout(isolated, capsys, monkeypatch):
    add("a", "a@example.com")
    add("b", "b@example.com")
    isolated.update(running=True, stuck=True)
    sleeps = []
    monkeypatch.setattr(ide.time, "sleep", sleeps.append)
    assert cli.main(["switch", "a"]) == 1
    assert "didn't quit in time" in capsys.readouterr().err
    assert sleeps == [1] * 15
    assert not any(call[0] == "open" for call in isolated["calls"])


def test_restore_rolls_back_on_insert_failure():
    add("a", "a@example.com")
    directory = Store().require("a")
    write_json(directory / "ide-auth.json", [
        {"key": "cursorAuth/accessToken", "value": "new"}, {"key": "fail", "value": "fail"}])
    import sqlite3
    with sqlite3.connect(ide.db_path()) as conn:
        conn.execute("CREATE TRIGGER reject BEFORE INSERT ON ItemTable WHEN NEW.key='fail' BEGIN SELECT RAISE(ABORT, 'test'); END")
    before = ide.live_rows()
    with pytest.raises(Error, match="couldn't write"):
        ide.restore(directory)
    assert ide.live_rows() == before


def test_locked_retry_limit(monkeypatch):
    import sqlite3
    add("a", "a@example.com")
    directory = Store().require("a")
    sleeps = []
    monkeypatch.setattr(ide.time, "sleep", sleeps.append)
    with sqlite3.connect(ide.db_path()) as locked:
        locked.execute("BEGIN IMMEDIATE")
        with pytest.raises(Error, match="couldn't write"):
            ide.restore(directory)
    assert sleeps == [1] * 4
    with sqlite3.connect(ide.db_path()) as locked:
        locked.execute("BEGIN IMMEDIATE")
        monkeypatch.setattr(ide.time, "sleep", lambda _: locked.rollback())
        ide.restore(directory)


def test_relative_db_and_corrupt_db(monkeypatch):
    database()
    monkeypatch.setenv("CURSOR_SWAP_IDE_DB", "state.vscdb")
    assert ide.live_token()
    ide.db_path().write_text("not sqlite")
    assert ide.live_rows() == []


def test_effective_token_prefers_live_for_active_account():
    add("a", "a@example.com")
    add("b", "b@example.com")
    store = Store()
    rotated = jwt("auth0|b", 5)
    database("b@example.com", rotated)
    assert usage.effective_access_token(store.require("b")) == rotated
    assert usage.effective_access_token(store.require("a")) == jwt("auth0|a")


def test_logout_local_keeps_session_and_saves_rotated_token(isolated, capsys):
    add("a", "a@example.com")
    rotated = jwt("auth0|a", 2)
    database(token=rotated, extra={"cursorAuth/cachedTeam": "team",
             **dict.fromkeys(ide.BYOK_KEYS, "user's-provider-key"), "unrelated": "keep"})
    isolated["running"] = True
    assert cli.main(["logout-local"]) == 0
    rows = ide_rows()
    assert not [k for k in rows if k.startswith("cursorAuth/") and k not in ide.BYOK_KEYS]
    assert all(rows[key] == "user's-provider-key" for key in ide.BYOK_KEYS)
    assert rows["unrelated"] == "keep"
    assert ide.row_value(read_json(Store().require("a") / "ide-auth.json"), "accessToken") == rotated
    assert ["open", "-a", "Cursor"] in isolated["calls"]
    assert "cursorswap add" in capsys.readouterr().out
    isolated["calls"].clear()
    assert cli.main(["ide-logout-local"]) == 0
    assert "nothing to do" in capsys.readouterr().out
    assert not isolated["calls"]


def test_logout_local_unsaved_session_needs_confirmation(isolated, monkeypatch):
    database(token=jwt("auth0|unsaved"))
    monkeypatch.delenv("CURSOR_SWAP_YES")
    with pytest.raises(SystemExit) as exc:
        cli.main(["logout-local"])
    assert exc.value.code == 1
    assert ide.live_token() == jwt("auth0|unsaved")
    assert not isolated["calls"]
