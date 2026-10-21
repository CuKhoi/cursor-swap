"""Every test is isolated from the user's credentials, app, home, and network."""
import io
import subprocess
from urllib.error import URLError

import pytest

from cursorswap import i18n, usage


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CURSOR_SWAP_STORE", str(tmp_path / "store"))
    monkeypatch.setenv("CURSOR_SWAP_IDE_DB", str(tmp_path / "state.vscdb"))
    monkeypatch.setenv("CURSOR_SWAP_YES", "1")
    monkeypatch.setenv("CURSOR_SWAP_LANG", "en")
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("CURSOR_SWAP_NO_UPDATE_CHECK", "1")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setattr(i18n, "LANG", "en")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    state = {"calls": [], "running": False}

    def run(args, **kwargs):
        state["calls"].append(list(args))
        assert args[0] in ("pgrep", "osascript", "open", "clear", "uv", "tasklist", "taskkill", "cmd"), args
        status, out = 0, ""
        if args[0] == "tasklist":
            assert args == ["tasklist", "/FI", "IMAGENAME eq Cursor.exe", "/NH"]
            out = "Cursor.exe  1234 Console  1  200,000 K" if state["running"] else "INFO: No tasks are running"
        elif args[0] == "taskkill":
            assert args == ["taskkill", "/IM", "Cursor.exe"]
            if not state.get("stuck"):
                state["running"] = False
        elif args[0] == "pgrep":
            assert args == ["pgrep", "-x", "Cursor"]
            status = 0 if state["running"] else 1
        elif args[0] == "osascript":
            assert args == ["osascript", "-e", 'quit app "Cursor"']
            if not state.get("stuck"):
                state["running"] = False
        return subprocess.CompletedProcess(args, status, out, "")

    def offline(*args, **kwargs):
        # Never reach Cursor's API; tests that need a response mock urlopen themselves.
        raise URLError("network disabled in tests")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(usage.request, "urlopen", offline)
    return state
