# cursorswap

English | [Tiếng Việt](README.vi.md)

Multi-account switcher for the **Cursor IDE** (Cursor.app) on macOS. Save several Cursor
logins and switch Cursor.app between them without logging in again each time.

> **CLI support is archived.** Earlier versions also switched the `cursor-agent` CLI
> (Keychain sessions, API keys, `run`/`map`). That code lives on the
> [`archive/cli-support`](https://github.com/CuKhoi/cursor-swap/tree/archive/cli-support)
> branch and will be revisited later; this version handles the IDE only.

## Install / update

```sh
curl -fsSL https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/install.sh | bash
```

The same one-liner installs, updates, and replaces an old Bash `cursorswap`. It installs
[uv](https://docs.astral.sh/uv/) if missing, then runs
`uv tool install --force git+https://github.com/CuKhoi/cursor-swap` (you can run that by
hand too). uv provisions Python 3.12+; there are no other dependencies. macOS only.

## Quick start

```sh
# 1. save the account Cursor.app is logged into now
cursorswap add work

# 2. sign the IDE out on this machine only - 'work' stays valid
cursorswap logout-local

# 3. log in to your other account in Cursor.app, then save it
cursorswap add personal

# from now on
cursorswap switch personal         # by name, slot number, alias or email
cursorswap switch                  # rotate to the next enabled account
cursorswap list                    # accounts, which one is active, usage %
```

`switch` and `logout-local` quit Cursor.app (asking first - this closes every IDE window),
write the session, and relaunch it. Pass `-y` or `export CURSOR_SWAP_YES=1` to skip the
prompt.

**Never use the IDE's own "Log out" to change accounts.** It revokes that session on
Cursor's server, so its saved snapshot stops working and you'd have to log in again and
re-run `add`. Use `logout-local` (deletes the auth rows on this machine only) to add an
account, and `switch` to change accounts.

## All commands

```
cursorswap add <name> [--alias A]   save the logged-in IDE account (re-run to refresh it)
cursorswap switch [<ref>]           switch to <ref>, or rotate to the next enabled account
cursorswap logout-local             sign the IDE out locally, without revoking the session
cursorswap list | usage [<ref>]     accounts + usage %, or usage % for one account
cursorswap alias <ref> <short>      short name (alias <ref> --unset, or alias to list)
cursorswap disable|enable <ref>     skip / include in 'switch' rotation
cursorswap remove <ref>             delete a saved account
cursorswap export|import <file>     back up / restore (plaintext tokens! import --force overwrites)
cursorswap renumber | watch [sec]   close slot gaps | repeat 'list' every N seconds
cursorswap purge | update | version | lang | help
```

`<ref>` is a profile name, slot number, alias or email. Old names still work as aliases:
`ide-add`, `ide-switch`/`ide-use`/`use`, `ide-logout-local`. `--lang vi` (or
`CURSOR_SWAP_LANG=vi`) switches all output to Vietnamese.

## How it works

Cursor.app keeps its login as plaintext rows - `cursorAuth/accessToken`,
`cursorAuth/refreshToken`, `cursorAuth/cachedEmail`, ... - in its local sqlite db
(`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`, table `ItemTable`)
and only reads them at startup. `add` snapshots those rows into
`~/.cursor-accounts/<name>/ide-auth.json`; `switch` quits the app, writes the target's rows
back in one transaction (clearing the previous account's `cursorAuth/*` rows, keeping your
own BYOK provider API keys), and relaunches it.

Found by reading Cursor.app's bundled JS (`out/vs/workbench/workbench.desktop.main.js`),
not from any documentation:

- **The IDE silently refreshes its token** (`POST /oauth/token`, about a week after the
  token was issued) and the old one then stops working. So before each switch cursorswap
  saves the outgoing account's live session back into its profile, matched by the JWT
  account id - your saved copy stays current as long as you switch with cursorswap.
- **The IDE's "Log out" calls `POST /auth/logout`**, revoking the session server-side -
  hence `logout-local`.

If a profile shows `session rejected` in `list`, its saved session was revoked: log in to
that account in Cursor.app again and re-run `cursorswap add <name>`.

**Usage %** comes from the same backend RPC the Cursor client uses
(`aiserver.v1.DashboardService/GetCurrentPeriodUsage`), called with the profile's token.
Undocumented, best-effort: on failure the reason is shown in place of the percentage.
Both this and the sqlite layout can change in any Cursor update - no stability guarantee.

## Data & security

Profiles live in `~/.cursor-accounts/<name>/` (or `CURSOR_SWAP_STORE`): directories mode
`700`, files mode `600`, written atomically. Tokens are plaintext - the same trust model as
Cursor.app's own `state.vscdb`, which already stores them unencrypted. Treat the store and
any `export` archive like a password file. `import` rejects links, devices and path
traversal.

## Development

```sh
git clone https://github.com/CuKhoi/cursor-swap && cd cursor-swap
uv sync
uv run pytest
bash tests/smoke.sh uv run cursorswap
```

Tests never touch the real store, Cursor.app or network: they set `CURSOR_SWAP_STORE` and
`CURSOR_SWAP_IDE_DB` to temp paths and stub `pgrep`/`osascript`/`open`. Setting the db
path alone does **not** stop a real running Cursor.app from being quit - stub `pgrep` too.

The Bash `cursorswap` and `cursor-swap` files are kept only so old installs' built-in
`update` keeps working; it points users at the installer above.

## License

MIT - see [LICENSE](LICENSE).
