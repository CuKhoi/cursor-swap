"""Command dispatch: multi-account switching for the Cursor.app IDE.

The cursor-agent CLI / API-key features are archived on the archive/cli-support
branch; profiles they created stay readable but are not switchable here.
"""
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time

from . import __version__, colors, i18n, ide, update_check, usage
from .i18n import t
from .store import Error, Store, label, read_json, write_json


def required(args, message, *values):
    if not args or not args[0]:
        raise Error(t(message, *values))
    return args[0]


def capture_args(args, message):
    name, alias = "", ""
    args = iter(args)
    for arg in args:
        if arg == "--alias":
            alias = next(args, None)
            if alias is None:
                raise Error(t(message))
        else:
            name = arg
    return required([name], message), alias


def display_email(meta):
    return meta.get("ide_email") or meta.get("email") or "?"


class CLI:
    def __init__(self, yes=False, force=False):
        self.store = Store()
        self.yes = yes
        self.force = force

    def confirm(self, message):
        if self.yes:
            return
        print(f"{colors.paint(message, 'yellow')} {t('confirm_suffix')} ", end="", file=sys.stderr, flush=True)
        answer = sys.stdin.readline().rstrip("\n")
        if answer.lower() != ("c" if i18n.LANG == "vi" else "y"):
            print(t("aborted"))
            raise SystemExit(1)

    def cmd_add(self, args):
        name, alias = capture_args(args, "usage_add")
        ide.capture(self.store, name, alias, self.confirm)

    def cmd_logout_local(self, args):
        ide.logout_local(self.store, self.confirm)

    def switch_to(self, directory):
        if directory == ide.active_profile(self.store):
            print(t("msg_already_on", label(directory), display_email(read_json(directory / "meta.json"))))
        else:
            ide.switch(self.store, directory, self.confirm)
        print(t("msg_usage_prefix", usage.field(usage.effective_access_token(directory))))

    def cmd_switch(self, args):
        if args:
            return self.switch_to(self.store.require(required(args, "usage_switch")))
        profiles = sorted((d for d in self.store.profiles()
                           if (d / "ide-auth.json").is_file() and read_json(d / "meta.json").get("enabled") is True),
                          key=lambda d: read_json(d / "meta.json")["slot"])
        if not profiles:
            raise Error(t("err_no_accounts_ide"))
        active = ide.active_profile(self.store)
        index = profiles.index(active) if active in profiles else -1
        self.switch_to(profiles[(index + 1) % len(profiles)])

    def cmd_list(self, args):
        self.store.ensure()
        active = ide.active_profile(self.store)
        print(t("hdr_accounts"))
        profiles = self.store.profiles()
        for directory in profiles:
            meta = read_json(directory / "meta.json")
            alias = meta.get("alias")
            has_ide = (directory / "ide-auth.json").is_file()
            tags = []
            if directory == active:
                tags.append(colors.bold_accent(t("tag_ide_active")))
            if meta.get("enabled") is False:
                tags.append(colors.muted(t("tag_disabled")))
            if not has_ide:
                tags.append(colors.muted(t("tag_no_ide")))
            slot_text = colors.bold(f"{str(meta['slot']) + ':':<3}")
            email_text = colors.accent(f"{display_email(meta):<28}")
            alias_text = colors.muted(f'"{alias}" ') if alias else ""
            tag_text = " " + " ".join(tags) if tags else ""
            print(f"  {slot_text} {email_text} {alias_text}{tag_text}")
            print(f"      {colors.muted(t('lbl_saved'))} {colors.muted(meta['saved_at'])}")
            if has_ide:
                print(f"      {colors.muted(t('lbl_usage'))} {usage.field(usage.effective_access_token(directory))}")
        if not profiles:
            print("  " + t("msg_none_saved_ide"))
        print()
        print(colors.muted(t("note_usage_line1")))
        print(colors.muted(t("note_usage_line2")))

    def cmd_usage(self, args):
        if args and args[0]:
            directory = self.store.require(args[0])
            if not (directory / "ide-auth.json").is_file():
                raise Error(t("err_no_ide_captured_ref", label(directory), args[0]))
            token = usage.effective_access_token(directory)
            text = label(directory)
        else:
            token = ide.live_token()
            if not token:
                raise Error(t("err_no_active_ide"))
            active = ide.active_profile(self.store)
            text = (label(active) if active else colors.accent(ide.current_email(self.store) or "?")) \
                + " " + colors.bold_accent(t("tag_ide_active"))
        if not token:
            raise Error(t("err_no_token", text))
        result, ok = usage.summary(token)
        if not ok:
            raise Error(t("err_usage_failed", result))
        print(f"{text}: {result}")

    def cmd_remove(self, args):
        directory = self.store.require(required(args, "usage_remove"))
        text = label(directory)
        self.confirm(t("confirm_delete", text))
        shutil.rmtree(directory)
        print(t("msg_removed", text))

    def cmd_enable_disable(self, args, state):
        directory = self.store.require(required(args, "usage_enable_disable", "enable" if state else "disable"))
        meta = read_json(directory / "meta.json")
        meta["enabled"] = state
        write_json(directory / "meta.json", meta)
        print(t("msg_enabled" if state else "msg_disabled", label(directory)))

    def cmd_alias(self, args):
        if not args:
            for directory in self.store.profiles():
                meta = read_json(directory / "meta.json")
                if meta.get("alias"):
                    print(f"  {meta['alias']:<15} -> {display_email(meta)}")
            return
        directory = self.store.require(args[0])
        alias = required(args[1:], "usage_alias")
        meta = read_json(directory / "meta.json")
        meta["alias"] = None if alias == "--unset" else alias
        write_json(directory / "meta.json", meta)
        print(t("msg_unset_alias", directory.name) if alias == "--unset" else t("msg_alias_set", alias, directory.name))

    def cmd_export(self, args):
        path = Path(required(args, "usage_export"))
        self.store.ensure()
        fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                with tarfile.open(fileobj=stream, mode="w:gz") as archive:
                    # Avoid including the archive itself when exporting inside the store.
                    excluded = {path.resolve(), Path(tmp).resolve()}
                    archive.add(self.store.path, arcname=".", filter=lambda member:
                                None if (self.store.path / member.name).resolve() in excluded else member)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            Path(tmp).unlink(missing_ok=True)
        count = sum(d.is_dir() for d in self.store.path.iterdir())
        print(t("msg_exported", count, path))
        print(t("warn_export_plaintext"))

    def cmd_import(self, args):
        path = Path(required(args, "usage_import"))
        self.store.ensure()
        if not path.is_file():
            raise Error(t("err_path_not_found", path))
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(path, "r:gz") as archive:
                # Archives contain credentials: reject links/devices and escaping paths.
                for member in archive.getmembers():
                    if not (member.isfile() or member.isdir()):
                        raise Error(t("err_unsafe_archive", member.name))
                archive.extractall(tmp, filter="data")
            for source in sorted(Path(tmp).iterdir()):
                if source.name.startswith(".") or not source.is_dir() or not (source / "meta.json").is_file():
                    continue
                directory = self.store.named(source.name)
                if directory.exists() and not self.force:
                    print(t("msg_skip_import", source.name))
                    continue
                read_json(source / "meta.json")
                # Secure every extracted file before moving the profile into the store.
                for item in source.rglob("*"):
                    item.chmod(0o700 if item.is_dir() else 0o600)
                source.chmod(0o700)
                if directory.exists():
                    shutil.rmtree(directory)
                shutil.move(str(source), directory)
                print(t("msg_imported", source.name))

    def cmd_purge(self, args):
        self.confirm(t("confirm_purge", self.store.path))
        if self.store.path.exists():
            shutil.rmtree(self.store.path)
        print(t("msg_purged", self.store.path))

    def cmd_version(self, args):
        print(f"cursorswap {__version__}")

    def cmd_lang(self, args):
        print(t("msg_lang_current", i18n.LANG))
        print(t("msg_lang_howto"))

    def cmd_watch(self, args):
        interval = int(args[0]) if args and re.fullmatch(r"[0-9]+", args[0]) else 30
        interval = max(5, interval)
        try:
            while True:
                ide.command(["clear"])
                print(colors.muted(t("msg_watch_header", interval)))
                print()
                self.cmd_list([])
                time.sleep(interval)
        except KeyboardInterrupt:
            print()

    def cmd_renumber(self, args):
        self.store.ensure()
        count = self.store.renumber()
        print(t("msg_renumbered", count) if count else "  " + t("msg_none_saved_ide"))

    def cmd_update(self, args):
        if shutil.which("uv"):
            # Same as install.sh: reinstall from GitHub main (a plain `uv tool upgrade`
            # can keep a cached git commit).
            ide.command(["uv", "tool", "install", "--force", "--python", "3.12", REPO], check=True)
        else:
            print(t("msg_update_no_uv"))

    def cmd_help(self, args):
        template = Path(__file__).with_name("help.txt").read_text()
        def replace(match):
            key = match[1]
            if key.startswith("t:"):
                parts = key.split(":")
                return t(parts[1], self.store.path) if len(parts) == 3 else t(parts[1])
            return colors.code(key)
        text = re.sub(r"\{([^{}]+)\}", replace, template)
        text = re.sub(r"^(  cursorswap [a-zA-Z][a-zA-Z-]*)", lambda m: colors.accent(m[0]), text, flags=re.M)
        print(text, end="")


REPO = "git+https://github.com/CuKhoi/cursor-swap"
ALIASES = {"ide-add": "add", "ide-switch": "switch", "ide-use": "switch", "use": "switch",
           "ide-logout-local": "logout-local", "ls": "list", "rm": "remove",
           "--version": "version", "-v": "version", "-h": "help", "--help": "help", "": "help"}
COMMANDS = {"add", "switch", "logout-local", "list", "usage", "remove", "enable", "disable", "alias",
            "export", "import", "purge", "version", "lang", "watch", "renumber", "update", "help"}
# CLI/API-key commands live on the archive/cli-support branch.
ARCHIVED = {"login", "add-token", "run", "map", "unmap", "status", "current"}


def main(argv=None):
    i18n.LANG = os.environ.get("CURSOR_SWAP_LANG") or "en"
    yes, force = os.environ.get("CURSOR_SWAP_YES") == "1", False
    args = []
    incoming = iter(sys.argv[1:] if argv is None else argv)
    for arg in incoming:
        if arg in ("-y", "--yes"):
            yes = True
        elif arg == "--force":
            force = True
        elif arg in ("-l", "--lang"):
            i18n.LANG = next(incoming, "en")
        elif arg.startswith("--lang="):
            i18n.LANG = arg.partition("=")[2]
        else:
            args.append(arg)
    command = args.pop(0) if args else "help"
    command = ALIASES.get(command, command)
    cli = CLI(yes, force)
    try:
        if command in ARCHIVED:
            raise Error(t("err_archived_command", command))
        if command not in COMMANDS:
            raise Error(t("err_unknown_command", command))
        if command in ("enable", "disable"):
            status = cli.cmd_enable_disable(args, command == "enable")
        else:
            status = getattr(cli, "cmd_" + command.replace("-", "_"))(args)
        update_check.notify(command)
        return status or 0
    except (Error, OSError, ValueError, tarfile.TarError, sqlite3.Error) as exc:
        print(colors.paint(t("err_prefix") + str(exc), "red"), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
