"""macOS Keychain tokens and the CLI's cached account configuration."""
import subprocess
from pathlib import Path

from .i18n import t
from .store import Error, atomic_write, metadata, private_dir, read_json, write_json


def config_path():
    return Path.home() / ".cursor/cli-config.json"


def command(args, quiet=False, check=False):
    result = subprocess.run(args, stdout=subprocess.DEVNULL if quiet else None,
                            stderr=subprocess.DEVNULL if quiet else None)
    if check and result.returncode:
        raise Error(f"{args[0]} exited with status {result.returncode}")
    return result.returncode


def secret_get(service):
    try:
        result = subprocess.run(["security", "find-generic-password", "-s", service,
                                 "-a", "cursor-user", "-w"], capture_output=True, text=True)
    except OSError:
        return None
    return result.stdout.rstrip("\n") if result.returncode == 0 else None


def has_session():
    return secret_get("cursor-access-token") is not None


def current_email():
    try:
        return read_json(config_path()).get("authInfo", {}).get("email") or "unknown"
    except (OSError, ValueError, AttributeError):
        return "unknown"


def capture(store, name, alias, confirm):
    access = secret_get("cursor-access-token")
    if access is None:
        raise Error(t("err_no_cli_access"))
    refresh = secret_get("cursor-refresh-token")
    if refresh is None:
        raise Error(t("err_no_cli_refresh"))
    if not config_path().is_file():
        raise Error(t("err_config_not_found", config_path()))
    directory = store.named(name)
    if directory.is_dir():
        meta = read_json(directory / "meta.json")
        confirm(t("confirm_overwrite", name, meta.get("email", "?")))
        slot = meta["slot"]
        alias = alias or meta.get("alias")
    else:
        slot = store.next_slot()
    private_dir(directory)
    atomic_write(directory / "access-token", access)
    atomic_write(directory / "refresh-token", refresh)
    atomic_write(directory / "cli-config.json", config_path().read_bytes())
    email = current_email()
    write_json(directory / "meta.json", metadata(email, slot, alias, "session"))
    print(t("msg_saved_cli", name, email, slot))


def restore(directory):
    for filename, service in (("access-token", "cursor-access-token"), ("refresh-token", "cursor-refresh-token")):
        command(["security", "add-generic-password", "-U", "-s", service,
                 "-a", "cursor-user", "-w", (directory / filename).read_text().rstrip("\n")], quiet=True, check=True)
    current = read_json(config_path())
    saved = read_json(directory / "cli-config.json")
    for key in ("authInfo", "autoReviewAvailabilityCache", "serverConfigCache"):
        current[key] = saved.get(key)
    write_json(config_path(), current)
