"""Command dispatch for the Bash-compatible profile store."""
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time

from . import __version__, cli_session, colors, i18n, ide, usage
from .i18n import t
from .store import Error, Store, atomic_write, label, metadata, private_dir, read_json, write_json


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
        self.store.ensure()
        got_cli = cli_session.has_session()
        if got_cli:
            cli_session.capture(self.store, name, alias, self.confirm)
        else:
            print(t("note_no_cli"))
        got_ide = bool(ide.live_token())
        if got_ide:
            ide.capture(self.store, name, alias)
        else:
            print(t("note_no_ide"))
        if not (got_cli or got_ide):
            raise Error(t("err_not_logged_in_anywhere"))

    def cmd_login(self, args):
        name = required(args, "usage_login")
        self.store.ensure()
        print(t("msg_logging_out"))
        cli_session.command(["agent", "logout"], quiet=True)
        print(t("msg_opening_browser"))
        cli_session.command(["agent", "login"], check=True)
        cli_session.capture(self.store, name, "", self.confirm)

    def cmd_add_token(self, args):
        self.store.ensure()
        token = required(args, "usage_add_token")
        email, alias = "", ""
        options = iter(args[1:])
        for arg in options:
            if arg in ("--email", "--alias"):
                value = next(options, None)
                if value is None:
                    raise Error(t("usage_add_token"))
                if arg == "--email":
                    email = value
                else:
                    alias = value
        if token == "-":
            token = sys.stdin.read().rstrip("\n")
        email = email or f"api-key-{self.store.next_slot()}@token.local"
        directory = self.store.named(email)
        if directory.is_dir():
            meta = read_json(directory / "meta.json")
            self.confirm(t("confirm_overwrite", email, meta.get("email", "?")))
            slot = meta["slot"]
            alias = alias or meta.get("alias")
        else:
            slot = self.store.next_slot()
        private_dir(directory)
        atomic_write(directory / "api-key", token)
        write_json(directory / "meta.json", metadata(email, slot, alias, "api-key"))
        print(t("msg_registered_api_key", email, slot))

    def cmd_ide_add(self, args):
        name, alias = capture_args(args, "usage_ide_add")
        ide.capture(self.store, name, alias)

    def cmd_ide_switch(self, args):
        ref = required(args, "usage_ide_switch")
        directory = self.store.require(ref)
        if not (directory / "ide-auth.json").is_file():
            raise Error(t("err_no_ide_captured_ref", label(directory), ref))
        ide.switch(self.store, directory, self.confirm)

    def cmd_ide_logout_local(self, args):
        ide.logout_local(self.store, self.confirm)

    def maybe_switch_ide(self, directory):
        if (directory / "ide-auth.json").is_file():
            ide.switch(self.store, directory, self.confirm)

    def switch_profile(self, directory):
        meta = read_json(directory / "meta.json")
        if meta["type"] == "api-key":
            raise Error(t("err_apikey_no_switch", label(directory), directory.name))
        if meta["type"] == "ide-only":
            print(t("msg_ide_only_switch", label(directory)))
            self.maybe_switch_ide(directory)
            print(t("msg_usage_prefix", usage.field(usage.effective_access_token(self.store, directory))))
            return
        if cli_session.current_email() == meta["email"] and cli_session.has_session():
            print(t("msg_already_on", label(directory), meta["email"]))
        else:
            cli_session.restore(directory)
            print(t("msg_swapped_verifying", label(directory)))
            cli_session.command(["agent", "status"], check=True)
            print(t("msg_usage_prefix", usage.field(cli_session.secret_get("cursor-access-token"))))
        self.maybe_switch_ide(directory)

    def cmd_use(self, args):
        self.switch_profile(self.store.require(required(args, "usage_switch")))

    def cmd_switch(self, args):
        if args:
            return self.cmd_use(args)
        now_email, now_ide = cli_session.current_email(), ide.current_email(self.store)
        profiles = [(d, read_json(d / "meta.json")) for d in self.store.profiles()]
        profiles = sorted(((d, m) for d, m in profiles if m["type"] in ("session", "ide-only")
                           and m.get("enabled") is True), key=lambda pair: pair[1]["slot"])
        if not profiles:
            raise Error(t("err_no_accounts"))
        index = -1
        if cli_session.has_session():
            index = next((i for i, (_, m) in enumerate(profiles)
                          if m["type"] == "session" and m["email"] == now_email), -1)
        if index == -1 and now_ide:
            index = next((i for i, (_, m) in enumerate(profiles) if m.get("ide_email") == now_ide), -1)
        self.switch_profile(profiles[(index + 1) % len(profiles)][0])

    def cmd_list(self, args):
        self.store.ensure()
        now_email, now_ide = cli_session.current_email(), ide.current_email(self.store)
        print(t("hdr_accounts"))
        profiles = self.store.profiles()
        for directory in profiles:
            meta = read_json(directory / "meta.json")
            kind, email = meta["type"], meta["email"]
            ide_email, alias = meta.get("ide_email"), meta.get("alias")
            tags = []
            if kind == "session" and email == now_email:
                tags.append(colors.bold_accent(t("tag_cli_active")))
            if ide_email and ide_email == now_ide:
                tags.append(colors.bold_accent(t("tag_ide_active")))
            if meta.get("enabled") is False:
                tags.append(colors.muted(t("tag_disabled")))
            if kind in ("api-key", "ide-only"):
                tags.append(colors.muted(t("tag_apikey" if kind == "api-key" else "tag_ideonly")))
            slot_text = colors.bold(f"{str(meta['slot']) + ':':<3}")
            email_text = colors.accent(f"{email:<28}")
            alias_text = colors.muted(f'"{alias}" ') if alias else ""
            tag_text = " " + " ".join(tags) if tags else ""
            print(f"  {slot_text} {email_text} {alias_text}{tag_text}")
            print(f"      {colors.muted(t('lbl_saved'))} {colors.muted(meta['saved_at'])}")
            if kind in ("session", "ide-only"):
                print(f"      {colors.muted(t('lbl_usage'))} {usage.field(usage.effective_access_token(self.store, directory))}")
            if ide_email and kind != "ide-only":
                print(f"      {colors.muted(t('lbl_ide'))}   {colors.muted(ide_email)}")
        if not profiles:
            print("  " + t("msg_none_saved"))
        print()
        print(colors.muted(t("note_usage_line1")))
        print(colors.muted(t("note_usage_line2")))

    def cmd_status(self, args):
        cli_session.command(["agent", "status"], check=True)
        cli_session.command(["agent", "about"], check=True)

    def cmd_usage(self, args):
        if args and args[0]:
            directory = self.store.require(args[0])
            kind = read_json(directory / "meta.json")["type"]
            if kind not in ("session", "ide-only"):
                raise Error(t("err_no_session_or_ide", label(directory), kind))
            token = usage.effective_access_token(self.store, directory)
            if not token:
                raise Error(t("err_no_token", label(directory)))
            text = label(directory)
        else:
            token = cli_session.secret_get("cursor-access-token")
            if token:
                text = colors.accent(cli_session.current_email()) + " " + colors.bold_accent(t("tag_cli_active"))
            else:
                token = ide.live_token()
                if not token:
                    raise Error(t("err_no_active_session"))
                text = colors.accent(ide.current_email(self.store)) + " " + colors.bold_accent(t("tag_ide_active"))
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
        directory = self.store.require(required(args, "usage_enable_disable", str(state).lower()))
        meta = read_json(directory / "meta.json")
        meta["enabled"] = state
        write_json(directory / "meta.json", meta)
        print(t("msg_enabled" if state else "msg_disabled", label(directory)))

    def cmd_alias(self, args):
        if not args:
            for directory in self.store.profiles():
                meta = read_json(directory / "meta.json")
                if meta.get("alias"):
                    print(f"  {meta['alias']:<15} -> {meta['email']}")
            return
        directory = self.store.require(args[0])
        alias = required(args[1:], "usage_alias")
        meta = read_json(directory / "meta.json")
        meta["alias"] = None if alias == "--unset" else alias
        write_json(directory / "meta.json", meta)
        print(t("msg_unset_alias", directory.name) if alias == "--unset" else t("msg_alias_set", alias, directory.name))

    def directory_path(self, args):
        path = Path(args[0]) if args else Path.cwd()
        if not path.is_dir():
            raise Error(t("err_path_not_dir", path))
        return str(path.resolve())

    def cmd_map(self, args):
        self.store.ensure()
        mappings = read_json(self.store.map_file)
        if not args:
            for path, name in mappings.items():
                print(f"  {name}  ->  {path}")
            return
        directory = self.store.require(args[0])
        path = self.directory_path(args[1:])
        mappings[path] = directory.name
        write_json(self.store.map_file, mappings)
        print(t("msg_mapped", path, label(directory)))

    def cmd_unmap(self, args):
        self.store.ensure()
        path = self.directory_path(args)
        mappings = read_json(self.store.map_file)
        mappings.pop(path, None)
        write_json(self.store.map_file, mappings)
        print(t("msg_unmapped", path))

    def cmd_run(self, args):
        if args and args[0] and args[0] != "--":
            ref, args = args[0], args[1:]
        else:
            ref = self.store.mapped_profile()
        if args and args[0] == "--":
            args = args[1:]
        if not ref:
            raise Error(t("err_no_account_no_mapping", Path.cwd()))
        directory = self.store.require(ref)
        kind = read_json(directory / "meta.json")["type"]
        if kind == "api-key":
            # Replace the process just as the Bash command does (including signals).
            os.execvp("agent", ["agent", "--api-key", (directory / "api-key").read_text().rstrip("\n"), *args])
        if kind != "session":
            raise Error(t("err_ideonly_no_run", label(directory)))
        for key in ("warn_run_line1", "warn_run_line2", "warn_run_line3"):
            print(t(key, label(directory)), file=sys.stderr)
        self.confirm(t("confirm_continue"))
        previous_email = cli_session.current_email()
        previous = next((d for d in self.store.profiles()
                         if (m := read_json(d / "meta.json"))["type"] == "session" and m["email"] == previous_email), None)
        cli_session.restore(directory)
        try:
            return cli_session.command(["agent", *args])
        finally:
            if previous:
                cli_session.restore(previous)
            else:
                print(t("note_prev_not_saved", previous_email), file=sys.stderr)

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
                cli_session.command(["clear"], quiet=False)
                print(colors.muted(t("msg_watch_header", interval)))
                print()
                self.cmd_list([])
                time.sleep(interval)
        except KeyboardInterrupt:
            print()

    def cmd_renumber(self, args):
        self.store.ensure()
        count = self.store.renumber()
        print(t("msg_renumbered", count) if count else "  " + t("msg_none_saved"))

    def cmd_update(self, args):
        if shutil.which("uv"):
            cli_session.command(["uv", "tool", "upgrade", "cursorswap"], check=True)
        else:
            print(t("msg_update_uv"))

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
    aliases = {"ide-use": "ide-switch", "ls": "list", "current": "status", "rm": "remove",
               "--version": "version", "-v": "version", "-h": "help", "--help": "help", "": "help"}
    command = aliases.get(command, command)
    cli = CLI(yes, force)
    try:
        if command in ("enable", "disable"):
            cli.cmd_enable_disable(args, command == "enable")
            return 0
        commands = {"add", "login", "add-token", "ide-add", "ide-switch", "ide-logout-local", "switch", "use", "list", "status",
                    "usage", "remove", "run", "map", "unmap", "alias", "export", "import", "purge", "version",
                    "lang", "watch", "renumber", "update", "help"}
        if command not in commands:
            raise Error(t("err_unknown_command", command))
        return getattr(cli, "cmd_" + command.replace("-", "_"))(args) or 0
    except (Error, OSError, ValueError, tarfile.TarError, sqlite3.Error) as exc:
        print(colors.paint(t("err_prefix") + str(exc), "red"), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
