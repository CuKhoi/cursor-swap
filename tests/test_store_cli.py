import io
import os
from pathlib import Path
import re
import tarfile

import pytest

from cursorswap import __version__, cli, cli_session, colors, i18n
from cursorswap.store import Error, Store, atomic_write, metadata, private_dir, read_json, write_json


def invoke(*args):
    return cli.main(list(args))


def profile(name, slot, alias=None, email=None, kind="api-key", enabled=True):
    store = Store()
    store.ensure()
    directory = store.named(name)
    private_dir(directory)
    meta = metadata(email or name + "@example.com", slot, alias, kind)
    meta["enabled"] = enabled
    write_json(directory / "meta.json", meta)
    return directory


def test_resolution_and_renumber():
    a = profile("a", 4, "first", "a@x")
    b = profile("b", 9, "second", "b@x")
    store = Store()
    for ref in ("a", "4", "first", "a@x"):
        assert store.require(ref) == a
    assert store.resolve("missing") is None
    with pytest.raises(Error, match="no account matches"):
        store.require("missing")
    assert store.next_slot() == 10
    write_json(store.map_file, {"/project": "b"})
    assert invoke("renumber") == 0
    assert read_json(a / "meta.json")["slot"] == 1
    assert read_json(b / "meta.json")["slot"] == 2
    assert read_json(b / "meta.json")["alias"] == "second"
    assert read_json(store.map_file) == {"/project": "b"}
    assert store.next_slot() == 3
    # Preserve Bash's alphabetical traversal when references collide.
    meta = read_json(a / "meta.json")
    meta["alias"] = "b"
    write_json(a / "meta.json", meta)
    assert store.require("b") == a


def test_smoke_round_trip(tmp_path, capsys):
    assert invoke("add-token", "sk-test", "--email", "ci@example.com", "--alias", "ci") == 0
    store = Store()
    directory = store.require("ci")
    assert (directory / "api-key").read_text() == "sk-test"
    assert invoke("ls") == 0
    assert "ci@example.com" in capsys.readouterr().out
    assert invoke("usage", "ci") == 1
    assert "api-key" in capsys.readouterr().err
    for command, expected in (("disable", False), ("enable", True)):
        assert invoke(command, "ci") == 0
        assert read_json(directory / "meta.json")["enabled"] is expected
    assert invoke("alias", "ci", "short") == 0
    assert invoke("alias") == 0
    assert "short" in capsys.readouterr().out
    assert invoke("map", "short", str(tmp_path)) == 0
    assert invoke("map") == 0
    assert "ci@example.com" in capsys.readouterr().out
    child = tmp_path / "nested"
    child.mkdir()
    os.chdir(child)
    assert store.mapped_profile() == directory.name
    assert invoke("unmap", str(tmp_path)) == 0
    assert store.mapped_profile() == ""
    assert invoke("alias", "short", "--unset") == 0
    assert read_json(directory / "meta.json")["alias"] is None
    assert invoke("alias", "1", "ci") == 0
    assert invoke("renumber") == 0
    assert invoke("map", "ci", str(tmp_path)) == 0
    backup = tmp_path / "backup.tar.gz"
    assert invoke("export", str(backup)) == 0
    assert backup.stat().st_mode & 0o777 == 0o600
    with tarfile.open(backup) as archive:
        assert "./mappings.json" in archive.getnames()
    assert invoke("rm", "ci") == 0
    assert invoke("import", str(backup)) == 0
    assert invoke("list") == 0
    assert "ci@example.com" in capsys.readouterr().out
    atomic_write(directory / "api-key", "changed")
    assert invoke("import", str(backup)) == 0
    assert "skip 'ci@example.com'" in capsys.readouterr().out
    assert (directory / "api-key").read_text() == "changed"
    assert invoke("--force", "import", str(backup)) == 0
    assert (directory / "api-key").read_text() == "sk-test"
    for path in store.path.rglob("*"):
        assert path.stat().st_mode & 0o777 == (0o700 if path.is_dir() else 0o600)
    assert store.path.stat().st_mode & 0o777 == 0o700
    assert invoke("remove", "ci") == 0
    assert invoke("purge") == 0
    assert not store.path.exists()
    assert invoke("import", str(backup)) == 0
    assert read_json(store.map_file) == {}  # Bash intentionally ignores imported mappings.


def test_stdin_default_email_and_overwrite(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("sk-from-stdin\n\n"))
    assert invoke("add-token", "-", "--alias", "one") == 0
    directory = Store().require("one")
    assert directory.name == "api-key-1@token.local"
    assert (directory / "api-key").read_text() == "sk-from-stdin"
    assert invoke("add-token", "new", "--email", directory.name) == 0
    assert read_json(directory / "meta.json")["alias"] == "one"
    assert read_json(directory / "meta.json")["slot"] == 1


@pytest.mark.parametrize("command", ["help", "--help", "-h", ""])
def test_help(command, capsys):
    assert invoke(command) == 0
    output = capsys.readouterr().out
    assert "cursorswap ide-switch" in output
    assert "uv tool upgrade cursorswap" in output
    assert "now feasible" in output
    assert "{t:" not in output


@pytest.mark.parametrize("command", ["version", "--version", "-v"])
def test_version(command, capsys):
    assert invoke(command) == 0
    assert capsys.readouterr().out == f"cursorswap {__version__}\n"


@pytest.mark.parametrize("args", [["unknown"], ["add"], ["login"], ["ide-add"], ["ide-switch"],
    ["use"], ["remove"], ["disable"], ["export"], ["import"], ["add", "--alias"],
    ["add-token", "key", "--email"], ["add-token", "key", "--email", "../escape"], ["run"]])
def test_errors(args, capsys):
    assert cli.main(args) == 1
    assert capsys.readouterr().err.startswith("error: ")


@pytest.mark.parametrize("flag", [["-l", "vi"], ["--lang", "vi"], ["--lang=vi"]])
def test_language_flags(flag, capsys):
    assert cli.main(["lang", *flag]) == 0
    assert "Ngôn ngữ hiện tại: vi" in capsys.readouterr().out
    assert cli.main([*flag, "unknown"]) == 1
    assert capsys.readouterr().err.startswith("lỗi: ")


def test_confirmation(monkeypatch, capsys):
    profile("one", 1)
    monkeypatch.setenv("CURSOR_SWAP_YES", "0")
    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    with pytest.raises(SystemExit) as exc:
        invoke("remove", "one")
    assert exc.value.code == 1
    assert Store().resolve("one")
    monkeypatch.setattr("sys.stdin", io.StringIO("C\n"))
    assert invoke("--lang=vi", "remove", "one") == 0
    assert not Store().resolve("one")
    assert "[c/K]" in capsys.readouterr().err
    assert invoke("-y", "purge") == 0
    assert invoke("--yes", "purge") == 0


def test_update(monkeypatch, isolated, capsys):
    monkeypatch.setattr(cli.shutil, "which", lambda name: "/fake/uv")
    assert invoke("update") == 0
    assert isolated["calls"][-1] == ["uv", "tool", "upgrade", "cursorswap"]
    monkeypatch.setattr(cli.shutil, "which", lambda name: None)
    assert invoke("update") == 0
    assert "uv tool upgrade cursorswap" in capsys.readouterr().out


def test_watch(monkeypatch, capsys, isolated):
    waits = []
    def sleep(seconds):
        waits.append(seconds)
        raise KeyboardInterrupt
    monkeypatch.setattr(cli.time, "sleep", sleep)
    for arg, interval in (("1", 5), ("10", 10), ("invalid", 30)):
        assert invoke("watch", arg) == 0
        assert waits[-1] == interval
    assert ["clear"] in isolated["calls"]


def test_colors_and_padded_list(monkeypatch, capsys):
    profile("a", 1, "alias", "test@example.com")
    assert not colors.supports_color()
    monkeypatch.setenv("FORCE_COLOR", "1")
    assert not colors.supports_color()  # NO_COLOR wins.
    monkeypatch.delenv("NO_COLOR")
    assert colors.supports_color()
    assert colors.sev_pct("69.9").startswith(colors.CODES["ok"])
    assert colors.sev_pct("70").startswith(colors.CODES["warn"])
    assert colors.sev_pct("90").startswith(colors.CODES["crit"])
    invoke("list")
    colored = capsys.readouterr().out
    assert colors.bold("1: ") in colored
    assert colors.accent(f"{'test@example.com':<28}") in colored
    monkeypatch.setenv("NO_COLOR", "1")
    invoke("list")
    assert re.sub(r"\x1b\[[0-9;]*m", "", colored) == capsys.readouterr().out
    monkeypatch.delenv("NO_COLOR")
    monkeypatch.delenv("FORCE_COLOR")
    monkeypatch.setattr("sys.stdout.isatty", lambda: True)
    monkeypatch.setenv("TERM", "dumb")
    assert not colors.supports_color()
    monkeypatch.setenv("TERM", "xterm")
    assert colors.supports_color()


@pytest.mark.parametrize("name,kind", [("../outside", "file"), ("/absolute", "file"), ("profile/link", "link")])
def test_import_rejects_unsafe_archive(tmp_path, name, kind, capsys):
    archive_path = tmp_path / "evil.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo(name)
        if kind == "link":
            info.type = tarfile.SYMTYPE
            info.linkname = "/tmp"
        else:
            info.size = 1
        archive.addfile(info, io.BytesIO(b"x") if kind == "file" else None)
    # tarfile's data filter strips leading '/' rather than rejecting it.
    if name.startswith("/"):
        assert invoke("import", str(archive_path)) == 0
    else:
        assert invoke("import", str(archive_path)) == 1
    assert not (tmp_path / "outside").exists()


def test_export_inside_store(tmp_path):
    assert invoke("add-token", "key") == 0
    path = Store().path / "backup.tar.gz"
    assert invoke("export", str(path)) == 0
    with tarfile.open(path) as archive:
        assert not any("tar.gz" in name for name in archive.getnames())


def test_atomic_write_failure_keeps_original(tmp_path, monkeypatch):
    path = tmp_path / "secret"
    atomic_write(path, "old")
    def fail(*args):
        raise OSError("rename failed")
    monkeypatch.setattr(os, "replace", fail)
    with pytest.raises(OSError):
        atomic_write(path, "new")
    assert path.read_text() == "old"
    assert not list(tmp_path.glob(".secret.*"))
