# cursorswap

English | [Tiếng Việt](README.vi.md)

> Renamed from `cursor-swap` (with a hyphen). If you installed the old name, running any
> `cursor-swap` command once will auto-fetch `cursorswap` and forward to it — nothing about
> your saved accounts changes. Use `cursorswap` from now on.

Multi-account switcher for the [Cursor CLI](https://cursor.com/cli) (`cursor-agent` / `agent`).
macOS only — Linux/Windows use a different, unverified credential storage mechanism.
[Help add support](CONTRIBUTING.md).

Save multiple Cursor logins (or API keys), switch between them, map a directory to an
account so `cursorswap run` in that folder always uses the right one.

## Why this exists

`agent login` only supports one active session per machine — the token lives in the macOS
Keychain (`cursor-access-token` / `cursor-refresh-token`, account `cursor-user`), not in a
per-project config file. `cursorswap` snapshots those Keychain items (plus the cached
`authInfo` in `~/.cursor/cli-config.json`) per named profile, and restores them on switch.

**Cursor.app's own login is a separate account from the CLI's** — switching one does not
touch the other. cursorswap manages both, independently: `add`/`login`/`switch`/`run` for
the CLI session (Keychain-based), `ide-add`/`ide-switch` for the Cursor.app IDE session
(sqlite-based, see below).

## Two account types

- **session** — a real browser login (`agent login`). Swapping to a session account
  overwrites the CLI's Keychain tokens **globally** — every terminal on the machine using
  `cursor-agent` sees the new account immediately. There is no way to run two session
  accounts concurrently in separate terminals; `CURSOR_DATA_DIR` was tested and does **not**
  scope auth per-process, so this is a hard OS-level constraint, not a missing feature.
- **api-key** — a Cursor API key (`agent --api-key ...` / `$CURSOR_API_KEY`). Never touches
  global state; passed per-invocation via `cursorswap run`. Safe to use concurrently across
  terminals/projects.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/install.sh | bash
```

Same one-liner to install, to update, and to migrate from the old Bash version (it
replaces `~/.local/bin/cursorswap`). It installs [uv](https://docs.astral.sh/uv/) if
missing, then `uv tool install --force git+https://github.com/CuKhoi/cursor-swap`, which
you can also run by hand. Python 3.12+ is provisioned by uv; there are zero runtime
Python dependencies and no `jq` or newer Bash needed. Install the
[`cursor-agent` CLI](https://cursor.com/cli) for CLI login/session commands; IDE-only use
just needs Cursor.app. macOS only.

Your profiles stay in `~/.cursor-accounts` (or `CURSOR_SWAP_STORE`); no migration is
needed. Both versions read the same files. `cursorswap update` now runs
`uv tool upgrade cursorswap`.

For development:

```sh
git clone https://github.com/CuKhoi/cursor-swap
cd cursor-swap
uv sync
uv run pytest
uv run cursorswap --help
```

The Bash `cursorswap` file stays in the repo so old installs' built-in `update` keeps
working (it now also prints how to switch to the Python version). `cursor-swap` remains a
compatibility shim; use `cursorswap`.

## Usage

```
# add an account - log into the CLI, the IDE, or both first, then:
cursorswap add personal            # captures whichever is logged in (CLI, IDE, or both)
cursorswap login work              # logout -> browser login -> save as "work" (CLI only)
cursorswap add-token sk-... --email work@co.com --alias work   # API key, no browser login

# list / status
cursorswap list                    # shows saved accounts, marks the active one, shows usage %
cursorswap status                  # `agent status` + `agent about`
cursorswap usage work              # usage % for one account (default: active)

# switch the global CLI session (and the IDE session too, if you ran ide-add for it)
cursorswap switch work             # by name, slot number, alias, or email - prints usage % after
cursorswap switch                  # rotate to the next enabled account - CLI, IDE-only,
                                     # or both; works fine if you only ever use the IDE

# run one command as a given account without touching the global session
# (only truly isolated for api-key profiles - see "Two account types" above)
cursorswap run work -- create-chat

# map a project directory to an account, then just run
cd ~/code/some-project
cursorswap map work
cursorswap run                     # auto-picks "work" from the directory mapping

# Cursor.app IDE account (separate login from the CLI - see "IDE account" below)
# 'add' above already captures it if the IDE was logged in - these are for re-capturing
# or swapping just the IDE side on its own.
cursorswap ide-add work            # (re-)snapshot ONLY the currently logged-in IDE session
cursorswap ide-switch work         # swap ONLY the IDE session, leave the CLI alone

# housekeeping
cursorswap alias 1 work            # short name for a slot
cursorswap disable work            # skip in rotation
cursorswap remove work
cursorswap export backup.tar.gz    # contains plaintext tokens - store securely
cursorswap import backup.tar.gz
cursorswap update                  # uv tool upgrade cursorswap
cursorswap version                 # print the installed version
cursorswap watch                   # repeat 'list' every 30s (pass a number to change it)
cursorswap renumber                # close gaps in slot numbers after removals

# language
cursorswap --lang vi list          # Vietnamese output for this one call
export CURSOR_SWAP_LANG=vi          # ...or set it once in your shell rc
```

Run `cursorswap --help` for the full command list.

## Usage % (undocumented API)

`agent status`/`agent about` expose no per-account quota. But the `cursor-agent` CLI's own
JS bundle calls a backend RPC — `aiserver.v1.DashboardService/GetCurrentPeriodUsage` — with
the same Bearer access-token cursorswap already stores per profile. `list`, `switch`, and
`usage` call it best-effort and print `total / auto / api` percent used.

This is **not a public/documented Cursor API** — found by reading the CLI's minified JS, not
from any spec. No stability guarantee; a Cursor update can silently break it, in which case
`list` and `switch` show a localized failure reason in place of the percentage;
`usage` exits non-zero when lookup fails. The active profile uses its live token.
Inactive snapshots can be rejected before JWT expiry; switching alone cannot repair
a revoked token. Log in again and re-run `add` / `ide-add` when that happens.

## IDE account (undocumented storage)

Cursor.app (the desktop editor) is a **separate login from the CLI** — it can be signed into
a different account entirely. Its session isn't in the Keychain at all; it's two plaintext
rows — `cursorAuth/accessToken` / `cursorAuth/refreshToken` — in the app's own local sqlite
db (`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`, `ItemTable`).
Found by reading that file (with the app quit, so its WAL journal was checkpointed) — not
the `Cursor Safe Storage` Keychain item, which is Electron's own encryption key for unrelated
things and isn't involved in the IDE's login at all.

- `cursorswap ide-add <name>` snapshots the currently-logged-in IDE session into a profile
  (works whether or not Cursor.app is running).
- `cursorswap ide-switch <ref>` restores **only** the IDE session, leaving the CLI alone.
- Once a profile has an IDE session captured, plain `cursorswap switch <ref>` swaps **both**
  — the CLI session, then the IDE one — in a single command. If a profile never had `ide-add`
  run on it, `switch` behaves exactly as before (CLI only, no IDE prompt).

Either way, swapping the IDE session requires the app **fully quit** first — it only reads
auth off disk at startup, and a live process can overwrite the write anyway. cursorswap
quits it for you (asks to confirm — this closes every open IDE window) and relaunches it
after. Pass `-y`/`--yes` to skip the confirmation, or `export CURSOR_SWAP_YES=1` in your
shell rc to always skip it (for every confirmation prompt in the tool, not just this one).

**Don't use the IDE's own "Log out" to change accounts** — it revokes that session on
Cursor's server, so the saved snapshot stops working and you'd have to log in again and
re-run `ide-add`. Switch with `cursorswap ide-switch` instead; it also re-saves the outgoing
account's session first, since Cursor silently refreshes its token every so often.

Same caveat as usage %: **undocumented on-disk format**, found by inspection, not from a
spec. A Cursor update can change it; if `ide-add`/`ide-switch` starts failing, that's likely
why — no stability guarantee.

## What this does NOT do

- **No auto-switch.** The usage % above comes from an undocumented endpoint that can change
  without notice — not something to build unattended automation on. Use `cursorswap watch`
  or `usage` yourself and switch manually.
- **TUI / menubar: not implemented.** Both are now feasible with the Python package,
  but neither is included. `watch` provides a terminal polling loop.
- **No true concurrent multi-session for browser-login accounts.** Confirmed via testing
  `CURSOR_DATA_DIR` — it does not isolate auth per process. If you need real concurrency,
  use `add-token` + `run` instead of session accounts.

## Language

`--lang <en|vi>` (or `CURSOR_SWAP_LANG=vi`) switches all of cursorswap's own output —
`list`, `switch`, errors, `--help`, everything — to Vietnamese. Command names and syntax
never translate (`cursorswap switch` is always `cursorswap switch`), only the
descriptions/messages around them. Falls back to English for anything not yet translated,
never to a blank line.

## Colors

`list`/`switch`/`usage` use a restrained color scheme (one warm accent, muted secondary
text, green/amber/red for usage % by severity) — off automatically when output isn't a
terminal (piped/redirected), and respects [`NO_COLOR`](https://no-color.org/) /
`FORCE_COLOR`.

## Data & security

Profiles are stored in `~/.cursor-accounts/<name>/` (dir mode `700`, token/key files mode
`600`) — plaintext on disk, same trust model as `cursor-agent`'s own `~/.cursor/cli-config.json`
and as `security find-generic-password` output. `ide-auth.json` (from `ide-add`) is plaintext
too, same trust model as Cursor.app's own `state.vscdb`, which already stores the same tokens
unencrypted. Anyone with read access to your user account can already read these; this tool
doesn't lower that bar, but treat the store (and any `export` archive) like a password file.

Python writes use private temporary files and atomic replacement: directories mode `700`,
all profile files mode `600`. Import accepts Bash exports, skips existing profiles unless
`--force` is supplied, and leaves `mappings.json` alone (matching Bash). Unsafe archive
links/devices and path traversal are rejected. Profile names must be visible single
directory names, not paths.

For isolated testing, set both `CURSOR_SWAP_STORE` and `CURSOR_SWAP_IDE_DB` to temporary
paths. A DB override alone does not prevent the real app from being quit: tests must
also mock `pgrep`, `osascript`, `open`, Keychain and `agent` calls. `uv run pytest` and
`bash tests/smoke.sh uv run cursorswap` already provide that isolation.

## License

MIT — see [LICENSE](LICENSE).
