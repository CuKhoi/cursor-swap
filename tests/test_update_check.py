import io
import json
import time

import pytest

from cursorswap import __version__, cli, update_check


class Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def tty(monkeypatch):
    monkeypatch.delenv("CURSOR_SWAP_NO_UPDATE_CHECK")
    monkeypatch.setattr(update_check, "interactive", lambda: True)


def serve(monkeypatch, version, calls):
    def urlopen(url, timeout):
        calls.append(url)
        return Response(f'__version__ = "{version}"\n'.encode())
    monkeypatch.setattr(update_check.request, "urlopen", urlopen)


def test_notice_once_a_day(tty, monkeypatch, capsys):
    calls = []
    serve(monkeypatch, "99.0.0", calls)
    assert cli.main(["list"]) == 0
    assert f"cursorswap 99.0.0 is available (you have {__version__})" in capsys.readouterr().err
    assert cli.main(["list"]) == 0  # cached: no second request, notice still shown
    assert "99.0.0" in capsys.readouterr().err
    assert len(calls) == 1
    cached = json.loads(update_check.cache_path().read_text())
    cached["checked_at"] = time.time() - update_check.INTERVAL - 1
    update_check.cache_path().write_text(json.dumps(cached))
    assert cli.main(["list"]) == 0
    assert len(calls) == 2


def test_no_notice_when_current_offline_or_disabled(tty, monkeypatch, capsys):
    calls = []
    serve(monkeypatch, __version__, calls)
    assert cli.main(["list"]) == 0
    assert "available" not in capsys.readouterr().err
    update_check.cache_path().unlink()
    monkeypatch.setattr(update_check.request, "urlopen", lambda *a, **kw: (_ for _ in ()).throw(OSError("offline")))
    assert cli.main(["list"]) == 0  # offline is silent
    assert "available" not in capsys.readouterr().err
    monkeypatch.setenv("CURSOR_SWAP_NO_UPDATE_CHECK", "1")
    update_check.cache_path().unlink()
    serve(monkeypatch, "99.0.0", calls)
    assert cli.main(["list"]) == 0
    assert "available" not in capsys.readouterr().err


def test_version_compare():
    assert update_check.parse("3.10.0") > update_check.parse("3.9.9")
    assert update_check.parse("v3.1") == (3, 1)
