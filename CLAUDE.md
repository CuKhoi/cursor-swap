# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`cursorswap` — a multi-account switcher for the **Cursor IDE** (Cursor.app) on macOS: it
snapshots Cursor.app's login into named profiles and restores them. A Python 3.12+ package
managed with uv, zero runtime dependencies (stdlib only).

**Scope is IDE-only.** `cursor-agent` CLI support (Keychain sessions, API keys,
`login`/`add-token`/`run`/`map`/`status`) was removed from `main` and archived on the
`archive/cli-support` branch, to be revisited later as a whole. Those commands now exit 1
with a pointer to the branch (`cli.ARCHIVED`). Don't re-add CLI pieces to `main` piecemeal.

## Commands

```bash
uv sync
uv run pytest
uv run cursorswap --help
bash tests/smoke.sh uv run cursorswap

# legacy bash files (must stay clean)
bash -n cursorswap cursor-swap install.sh
shellcheck cursorswap cursor-swap install.sh tests/smoke.sh
```

`tests/conftest.py` isolates HOME, store and IDE DB for every test, stubs `subprocess.run`
(only `pgrep`/`osascript`/`open`/`clear`/`uv` allowed) and makes `urlopen` fail offline.
`tests/helpers.py` fakes IDE logins (`database()`, `jwt()`, `add()`). `tests/smoke.sh`
runs the real console command against a scratch store + fake sqlite db with shell stubs.

**Never test destructive commands (`remove`, `purge`, `switch`, `logout-local`) against
the real store or IDE db.** Set both `CURSOR_SWAP_STORE` and `CURSOR_SWAP_IDE_DB` to temp
paths — and stub `pgrep` to `exit 1`: the db override alone does **not** stop `switch` from
quitting a really-running Cursor.app. A prior session deleted a real saved profile this way.

## Architecture

- `cli.py` — global flag stripping (`-y`/`--yes`, `--force`, `-l`/`--lang`, `--lang=`),
  `ALIASES` (`ide-add`→`add`, `ide-switch`/`ide-use`/`use`→`switch`,
  `ide-logout-local`→`logout-local`, `ls`, `rm`, ...), `COMMANDS`, `ARCHIVED`, and all
  `CLI.cmd_*` handlers. Expected errors → stderr, exit 1.
- `ide.py` — everything about Cursor.app: `live_rows()` (read-only sqlite URI),
  `capture()`, `save_back()`, `restore()`/`replace_auth_rows()`, `quit_app()`/`relaunch()`,
  `switch()`, `logout_local()`, JWT `sub` matching (`profile_for_sub`, `active_profile`),
  and the `command()` subprocess helper.
- `store.py` — profile dirs, `meta.json`, slots/renumber, reference lookup, private dirs and
  atomic mode-600 writes.
- `usage.py` — usage % RPC; `effective_access_token()` prefers the live token when the
  profile is the account Cursor.app is signed into.
- `i18n.py`, `colors.py`, `help.txt` — EN/VI catalogs, ANSI palette, help template.
- `__init__.py` — version (single source of truth).

### The IDE session (undocumented)

Cursor.app keeps its login as plaintext rows (`cursorAuth/accessToken`,
`cursorAuth/refreshToken`, `cursorAuth/cachedEmail`, `cachedTeam`, `stripe*`, ...) in
`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb`, table `ItemTable`,
and reads them only at startup — so `switch` must quit the app first, write, then relaunch.

Profiles are matched to the live session by the access token's JWT `sub` (auth0 account
id), not by email: `cachedEmail` can lag after login and tokens rotate, but `sub` is stable.

Findings from reading Cursor.app 3.25.9's `out/vs/workbench/workbench.desktop.main.js` (auth
service: `_performAccessTokenRefresh` / `logout` / `revokeCursorSession`):

- **Silent refresh rotation.** `POST {backendUrl}/oauth/token` with
  `{grant_type:"refresh_token", client_id:<cursorCreds.authClientId>, refresh_token}` once
  the JWT is within `U8m = 1272h` (~53 days) of `exp` — about a week after issue. The
  response's `access_token` is stored under *both* keys (why they're byte-identical); the
  old token then gets rejected (HTTP 401 `ERROR_NOT_LOGGED_IN` while `exp` is still months
  out). `save_back()` runs before every restore/logout and re-snapshots the outgoing live
  rows into the profile with the same `sub`, so rotated tokens are kept.
- **IDE "Log out" revokes server-side** (`POST {backendUrl}/auth/logout`), killing that
  profile's snapshot. `logout-local` is the safe substitute: quit, save-back,
  `replace_auth_rows([])`, relaunch — the IDE starts signed out without calling the server.
  It confirms first if the live session isn't saved in any profile.

`replace_auth_rows()` deletes every `cursorAuth/*` row except the BYOK provider keys
(`ide.BYOK_KEYS`) and inserts the snapshot in one `BEGIN IMMEDIATE` transaction (parameterized
queries), retrying 5x on "database is locked" — a helper process can hold the lock briefly
after the app quits.

### Profile store

`~/.cursor-accounts/<name>/` (`CURSOR_SWAP_STORE`): `meta.json` (`email`, `ide_email`,
`slot`, `alias`, `type`, `enabled`, `saved_at`) + `ide-auth.json` (`[{key, value}]` rows).
New profiles are `type: "ide-only"`. Profiles left over from the CLI era (`session` /
`api-key`, no `ide-auth.json`) still list, tagged as archived, but aren't switchable. The
format is shared with the legacy Bash tool. Reference lookup walks profiles alphabetically,
checking name, slot, alias, then email per dir.

### Usage % (undocumented)

`aiserver.v1.DashboardService/GetCurrentPeriodUsage` on `api2.cursor.sh`, bearer token,
best-effort. Failures render a localized reason in place of the % (no token / network /
401-403 "session rejected" / other HTTP / bad shape) — never a blank line. "Rejected", not
"revoked": a never-valid token lands in the same bucket.

### i18n

`t(key, *args)` substitutes `{1}`/`{2}` placeholders (not `%` formatting — messages contain
literal `%`) and falls back vi → en → key, never empty. The original MSG_EN/MSG_VI entries
are verbatim copies of the Bash catalog (`test_catalog_matches_every_bash_message`
enforces this), so IDE-edition text goes in **new** keys (`*_ide`) appended at the bottom,
never by overwriting a Bash key.

### Colors

Off when stdout isn't a tty, `NO_COLOR` wins over `FORCE_COLOR`, `TERM=dumb` disables. In
`list`, pad plain text to width **before** colorizing — ANSI codes count toward the width.

### Legacy files — keep them

- `cursorswap` (Bash) and `cursor-swap` (old-name shim): pre-Python installs self-update by
  downloading these exact GitHub raw paths. Deleting or breaking them breaks those installs.
  Bash `update` prints how to switch to the Python installer. The Bash script still has the
  CLI features — it's frozen legacy, not the spec anymore.
- `install.sh` — the one-liner users pipe from GitHub raw: installs uv if missing, then
  `uv tool install --force` (the checkout when run from one, else `git+` main; `--force`
  replaces an old Bash `cursorswap`), plus the `cursor-swap` shim. Optional arg = bin dir.

### CI can sit "queued" for a long time — not a code problem

GitHub's `macos-latest` runners have had real queue congestion (a run once sat ~1h and
failed "job was not acquired by Runner"). Trust a clean local pytest + smoke + shellcheck.
