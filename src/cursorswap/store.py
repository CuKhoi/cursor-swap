"""Profile files, slots and directory mappings shared with the Bash tool."""
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from .colors import accent, muted
from .i18n import t


class Error(Exception):
    """A user-facing error (printed once by the command dispatcher)."""


def read_json(path):
    return json.loads(Path(path).read_text())


def private_dir(path):
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    path.chmod(0o700)


def atomic_write(path, data):
    """mkstemp creates mode 600 before any secret bytes are written."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data.encode() if isinstance(data, str) else data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)


def write_json(path, value):
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def metadata(email, slot, alias, kind):
    return dict(email=email, saved_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                slot=slot, alias=alias or None, type=kind, enabled=True)


def label(directory):
    alias = read_json(directory / "meta.json").get("alias")
    return accent(directory.name) + (" " + muted(f"({alias})") if alias else "")


class Store:
    def __init__(self):
        self.path = Path(os.environ.get("CURSOR_SWAP_STORE") or Path.home() / ".cursor-accounts")
        self.map_file = self.path / "mappings.json"

    def ensure(self):
        private_dir(self.path)
        if not self.map_file.is_file():
            write_json(self.map_file, {})

    def profiles(self):
        return sorted(p.parent for p in self.path.glob("*/meta.json")
                      if p.is_file() and not p.parent.name.startswith(".") and not p.parent.is_symlink())

    def named(self, name):
        # A profile is one directory, never an arbitrary filesystem path.
        if not name or name.startswith(".") or "/" in name or "\0" in name:
            raise Error(t("err_no_match", name))
        directory = self.path / name
        if directory.is_symlink():
            raise Error(t("err_no_match", name))
        return directory

    def next_slot(self):
        return max((read_json(d / "meta.json").get("slot") or 0 for d in self.profiles()), default=0) + 1

    def resolve(self, ref):
        # Bash visits profiles in name order, checking name/slot/alias/email for each.
        for directory in self.profiles():
            meta = read_json(directory / "meta.json")
            if ref in (directory.name, str(meta.get("slot")), meta.get("alias") or "", meta.get("email")):
                return directory
        return None

    def require(self, ref):
        directory = self.resolve(ref)
        if directory is None:
            raise Error(t("err_no_match", ref))
        return directory

    def renumber(self):
        directories = sorted(self.profiles(), key=lambda d: read_json(d / "meta.json")["slot"])
        for slot, directory in enumerate(directories, 1):
            meta = read_json(directory / "meta.json")
            meta["slot"] = slot
            write_json(directory / "meta.json", meta)
        return len(directories)

