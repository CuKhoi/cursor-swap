"""Once-a-day "new version available" notice, read from GitHub main. Best-effort:
any failure (offline, timeout, GitHub down) is silent and never slows a command
by more than the short timeout. Disable with CURSOR_SWAP_NO_UPDATE_CHECK=1."""
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib import request

from . import __version__
from .colors import paint
from .i18n import t

URL = "https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/src/cursorswap/__init__.py"
INTERVAL = 24 * 3600


def parse(version):
    return tuple(int(part) for part in re.findall(r"\d+", version)[:3])


def cache_path():
    return Path.home() / ".cache" / "cursorswap" / "update-check.json"


def latest_version():
    path = cache_path()
    try:
        cached = json.loads(path.read_text())
        if time.time() - cached["checked_at"] < INTERVAL:
            return cached["latest"]
    except (OSError, ValueError, KeyError, TypeError):
        pass
    try:
        with request.urlopen(URL, timeout=2) as response:
            latest = re.search(r'__version__ = "([^"]+)"', response.read().decode())[1]
    except Exception:  # noqa: BLE001 - a notice must never break a command
        latest = ""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"checked_at": time.time(), "latest": latest}))
    except OSError:
        pass
    return latest


def interactive():
    return sys.stderr.isatty()


def notify(command):
    if os.environ.get("CURSOR_SWAP_NO_UPDATE_CHECK") == "1" or command in ("update", "version") \
            or not interactive():
        return
    latest = latest_version()
    if latest and parse(latest) > parse(__version__):
        print(paint(t("msg_update_available", latest, __version__), "yellow"), file=sys.stderr)
