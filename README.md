# cursor-swap

Multi-account switcher for the [Cursor CLI](https://cursor.com/cli) (`cursor-agent` / `agent`), inspired by
`cswap` for Claude Code. macOS only.

Save multiple Cursor logins (or API keys), switch between them, map a directory to an
account so `cursor-swap run` in that folder always uses the right one.

## Why this exists

`agent login` only supports one active session per machine — the token lives in the macOS
Keychain (`cursor-access-token` / `cursor-refresh-token`, account `cursor-user`), not in a
per-project config file. `cursor-swap` snapshots those Keychain items (plus the cached
`authInfo` in `~/.cursor/cli-config.json`) per named profile, and restores them on switch.

**This is different from Cursor's IDE account.** The Keychain items above belong to the CLI
only — the Cursor.app desktop editor uses a separate item (`Cursor Safe Storage`) for its own
local-storage encryption, so switching CLI accounts does not touch a running IDE session.
(Verified by inspecting Keychain item metadata; not touched or read by this tool.)

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
# add an account
cursor-swap login work              # logout -> browser login -> save as "work"
cursor-swap add personal            # snapshot the currently logged-in session as "personal"
cursor-swap add-token sk-... --email work@co.com --alias work   # API key, no browser login

# list / status
cursor-swap list                    # shows saved accounts, marks the active one
cursor-swap status                  # `agent status` + `agent about`

# switch the global CLI session
cursor-swap switch work             # by name, slot number, alias, or email
cursor-swap switch                  # rotate to the next enabled session account

# run one command as a given account without touching the global session
# (only truly isolated for api-key profiles - see "Two account types" above)
cursor-swap run work -- create-chat

# map a project directory to an account, then just run
cd ~/code/some-project
cursor-swap map work
cursor-swap run                     # auto-picks "work" from the directory mapping

# housekeeping
cursor-swap alias 1 work            # short name for a slot
cursor-swap disable work            # skip in rotation
cursor-swap remove work
cursor-swap export backup.tar.gz    # contains plaintext tokens - store securely
cursor-swap import backup.tar.gz
```

Run `cursor-swap --help` for the full command list.

## What this does NOT do

Checked against the actual Cursor CLI (`agent about`, `agent status --help`) before deciding
these were out of scope, not just skipped:

- **No usage/quota display.** Cursor CLI exposes no per-account rate-limit percentage or
  reset time, so there's no `switch --strategy best` / auto-switch-near-limit like cswap has
  for Claude — there's nothing to compute it from.
- **No dashboard (tui/watch/menubar).** Same reason: no quota data to visualize.
- **No true concurrent multi-session for browser-login accounts.** Confirmed via testing
  `CURSOR_DATA_DIR` — it does not isolate auth per process. If you need real concurrency,
  use `add-token` + `run` instead of session accounts.

## Data & security

Profiles are stored in `~/.cursor-accounts/<name>/` (dir mode `700`, token/key files mode
`600`) — plaintext on disk, same trust model as `cursor-agent`'s own `~/.cursor/cli-config.json`
and as `security find-generic-password` output. Anyone with read access to your user account
can already read the live Keychain item; this tool doesn't lower that bar, but treat the
store (and any `export` archive) like a password file.

## License

MIT — see [LICENSE](LICENSE).
