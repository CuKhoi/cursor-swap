# cursor-swap

English | [Tiếng Việt](README.vi.md)

Multi-account switcher for the [Cursor CLI](https://cursor.com/cli) (`cursor-agent` / `agent`).
macOS only — Linux/Windows use a different, unverified credential storage mechanism.
[Help add support](CONTRIBUTING.md).

Save multiple Cursor logins (or API keys), switch between them, map a directory to an
account so `cursor-swap run` in that folder always uses the right one.

## Why this exists

`agent login` only supports one active session per machine — the token lives in the macOS
Keychain (`cursor-access-token` / `cursor-refresh-token`, account `cursor-user`), not in a
per-project config file. `cursor-swap` snapshots those Keychain items (plus the cached
`authInfo` in `~/.cursor/cli-config.json`) per named profile, and restores them on switch.

**Cursor.app's own login is a separate account from the CLI's** — switching one does not
touch the other. cursor-swap manages both, independently: `add`/`login`/`switch`/`run` for
the CLI session (Keychain-based), `ide-add`/`ide-switch` for the Cursor.app IDE session
(sqlite-based, see below).

## Two account types

- **session** — a real browser login (`agent login`). Swapping to a session account
  overwrites the CLI's Keychain tokens **globally** — every terminal on the machine using
  `cursor-agent` sees the new account immediately. There is no way to run two session
  accounts concurrently in separate terminals; `CURSOR_DATA_DIR` was tested and does **not**
  scope auth per-process, so this is a hard OS-level constraint, not a missing feature.
- **api-key** — a Cursor API key (`agent --api-key ...` / `$CURSOR_API_KEY`). Never touches
  global state; passed per-invocation via `cursor-swap run`. Safe to use concurrently across
  terminals/projects.

## Install

```
curl -fsSL https://raw.githubusercontent.com/CuKhoi/cursor-switch/main/install.sh | bash
```

Installs to `~/.local/bin/cursor-swap`. Pass a different directory as an arg if you don't
want that: `curl -fsSL .../install.sh | bash -s -- /usr/local/bin`.

Or clone and run it locally:

```
git clone git@github.com:CuKhoi/cursor-switch.git
cd cursor-switch
./install.sh
```

Requires `jq` (`brew install jq`) and the [`cursor-agent` CLI](https://cursor.com/cli) already
installed.

## Usage

```
# add an account - log into the CLI, the IDE, or both first, then:
cursor-swap add personal            # captures whichever is logged in (CLI, IDE, or both)
cursor-swap login work              # logout -> browser login -> save as "work" (CLI only)
cursor-swap add-token sk-... --email work@co.com --alias work   # API key, no browser login

# list / status
cursor-swap list                    # shows saved accounts, marks the active one, shows usage %
cursor-swap status                  # `agent status` + `agent about`
cursor-swap usage work              # usage % for one account (default: active)

# switch the global CLI session (and the IDE session too, if you ran ide-add for it)
cursor-swap switch work             # by name, slot number, alias, or email - prints usage % after
cursor-swap switch                  # rotate to the next enabled account - CLI, IDE-only,
                                     # or both; works fine if you only ever use the IDE

# run one command as a given account without touching the global session
# (only truly isolated for api-key profiles - see "Two account types" above)
cursor-swap run work -- create-chat

# map a project directory to an account, then just run
cd ~/code/some-project
cursor-swap map work
cursor-swap run                     # auto-picks "work" from the directory mapping

# Cursor.app IDE account (separate login from the CLI - see "IDE account" below)
# 'add' above already captures it if the IDE was logged in - these are for re-capturing
# or swapping just the IDE side on its own.
cursor-swap ide-add work            # (re-)snapshot ONLY the currently logged-in IDE session
cursor-swap ide-switch work         # swap ONLY the IDE session, leave the CLI alone

# housekeeping
cursor-swap alias 1 work            # short name for a slot
cursor-swap disable work            # skip in rotation
cursor-swap remove work
cursor-swap export backup.tar.gz    # contains plaintext tokens - store securely
cursor-swap import backup.tar.gz
cursor-swap update                  # pull the latest cursor-swap from GitHub, replace self
cursor-swap version                 # print the installed version
```

Run `cursor-swap --help` for the full command list.

## Usage % (undocumented API)

`agent status`/`agent about` expose no per-account quota. But the `cursor-agent` CLI's own
JS bundle calls a backend RPC — `aiserver.v1.DashboardService/GetCurrentPeriodUsage` — with
the same Bearer access-token cursor-swap already stores per profile. `list`, `switch`, and
`usage` call it best-effort and print `total / auto / api` percent used.

This is **not a public/documented Cursor API** — found by reading the CLI's minified JS, not
from any spec. No stability guarantee; a Cursor update can silently break it, in which case
these commands just show nothing (they never hard-fail because of it). Usage % for a saved
but currently-inactive profile depends on that profile's snapshotted access-token still being
valid — if it's expired, `switch` to that account once to refresh it.

## IDE account (undocumented storage)

Cursor.app (the desktop editor) is a **separate login from the CLI** — it can be signed into
a different account entirely. Its session isn't in the Keychain at all; it's two plaintext
rows — `cursorAuth/accessToken` / `cursorAuth/refreshToken` — in the app's own local sqlite
db (`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`, `ItemTable`).
Found by reading that file (with the app quit, so its WAL journal was checkpointed) — not
the `Cursor Safe Storage` Keychain item, which is Electron's own encryption key for unrelated
things and isn't involved in the IDE's login at all.

- `cursor-swap ide-add <name>` snapshots the currently-logged-in IDE session into a profile
  (works whether or not Cursor.app is running).
- `cursor-swap ide-switch <ref>` restores **only** the IDE session, leaving the CLI alone.
- Once a profile has an IDE session captured, plain `cursor-swap switch <ref>` swaps **both**
  — the CLI session, then the IDE one — in a single command. If a profile never had `ide-add`
  run on it, `switch` behaves exactly as before (CLI only, no IDE prompt).

Either way, swapping the IDE session requires the app **fully quit** first — it only reads
auth off disk at startup, and a live process can overwrite the write anyway. cursor-swap
quits it for you (asks to confirm — this closes every open IDE window) and relaunches it
after. Pass `-y`/`--yes` to skip the confirmation, or `export CURSOR_SWAP_YES=1` in your
shell rc to always skip it (for every confirmation prompt in the tool, not just this one).

Same caveat as usage %: **undocumented on-disk format**, found by inspection, not from a
spec. A Cursor update can change it; if `ide-add`/`ide-switch` starts failing, that's likely
why — no stability guarantee.

## What this does NOT do

- **No auto-switch / tui / watch / menubar.** The usage % above comes from an undocumented
  endpoint that can change without notice — not something to build unattended automation on.
  Use `cursor-swap usage` yourself and switch manually.
- **No true concurrent multi-session for browser-login accounts.** Confirmed via testing
  `CURSOR_DATA_DIR` — it does not isolate auth per process. If you need real concurrency,
  use `add-token` + `run` instead of session accounts.

## Data & security

Profiles are stored in `~/.cursor-accounts/<name>/` (dir mode `700`, token/key files mode
`600`) — plaintext on disk, same trust model as `cursor-agent`'s own `~/.cursor/cli-config.json`
and as `security find-generic-password` output. `ide-auth.json` (from `ide-add`) is plaintext
too, same trust model as Cursor.app's own `state.vscdb`, which already stores the same tokens
unencrypted. Anyone with read access to your user account can already read these; this tool
doesn't lower that bar, but treat the store (and any `export` archive) like a password file.

## License

MIT — see [LICENSE](LICENSE).
