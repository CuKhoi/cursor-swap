"""Every test is isolated from the user's credentials, app, home, and network."""
import io
import subprocess

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
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setattr(i18n, "LANG", "en")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    state = {"calls": [], "secrets": {}, "agent_status": 0, "running": False}

    def run(args, **kwargs):
        state["calls"].append(list(args))
        assert args[0] in ("security", "pgrep", "osascript", "open", "agent", "clear", "uv"), args
        status, output = 0, ""
        if args[0] == "security":
            service = args[args.index("-s") + 1]
            if args[1] == "find-generic-password":
                status = 0 if service in state["secrets"] else 1
                output = state["secrets"].get(service, "") + "\n"
            else:
                assert args[1] == "add-generic-password"
                state["secrets"][service] = args[args.index("-w") + 1]
        elif args[0] == "pgrep":
            assert args == ["pgrep", "-x", "Cursor"]
            status = 0 if state["running"] else 1
        elif args[0] == "osascript":
            assert args == ["osascript", "-e", 'quit app "Cursor"']
            if not state.get("stuck"):
                state["running"] = False
        elif args[0] == "agent":
            status = state["agent_status"]
        return subprocess.CompletedProcess(args, status, output, "")

    def execvp(file, args):
        assert file == "agent"
        state["calls"].append(list(args))
        raise SystemExit(state["agent_status"])

    def no_network(*args, **kwargs):
        raise AssertionError("Network must be mocked explicitly")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr("os.execvp", execvp)
    monkeypatch.setattr(usage.request, "urlopen", no_network)
    return state
