# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`cursorswap` — a Python 3.12+ package managed with uv, with zero runtime Python
dependencies. It snapshots and restores Cursor CLI and Cursor.app logins on macOS.
The original Bash tool remains available for existing installs, with identical storage.

## Commands

```bash
# syntax + lint (must both be clean before committing)
bash -n cursorswap cursor-swap install.sh
shellcheck cursorswap cursor-swap install.sh    # brew install shellcheck if missing

uv sync
uv run pytest
uv run cursorswap --help
bash tests/smoke.sh uv run cursorswap
```

`tests/conftest.py` isolates HOME, store, and IDE DB for every test, mocks all subprocess
calls and API-key exec, and blocks unmocked HTTP. IDE tests use temporary sqlite databases
and fake JWTs. `tests/smoke.sh` isolates the console commands in the same way, using shell
stubs for system commands. **Never test destructive commands against the real store.**
Always set both `CURSOR_SWAP_STORE` and `CURSOR_SWAP_IDE_DB` to temporary paths and mock
`security`, `pgrep`, `osascript`, `open`, and `agent`. The DB override does not prevent
quitting the real Cursor.app. A prior session accidentally deleted a real saved profile.

CI (`.github/workflows/ci.yml`) runs on `macos-latest` specifically — the tool is
macOS-only and the smoke test exercises real commands, not just static analysis.

## Architecture

### Python layout

- `pyproject.toml`: hatchling, console entry point `cursorswap.cli:main`, pytest dev group.
  `uv.lock` locks development dependencies; runtime dependencies are empty.
- `src/cursorswap/__init__.py`: single source of truth for Python version 2.0.0.
- `cli.py`: global flag stripping, aliases, all command handlers, confirmations, archives.
- `store.py`: Bash-compatible profiles/mappings, reference lookup, slots/renumber,
  private directories and atomic mode-600 writes.
- `cli_session.py`: Keychain and CLI config capture/restore; restores only the three
  account-specific config keys, preserving other local preferences.
- `ide.py`: parameterized sqlite reads/writes, JWT subject matching, outgoing save-back,
  and quit/restore/relaunch. Restore is one transaction; retry locked DBs five times.
- `usage.py`: urllib POST with a four-second timeout; live tokens preferred for active
  profiles, with localized failure reasons and one-decimal percentages.
- `i18n.py`, `colors.py`, `help.txt`: verbatim EN/VI Bash catalogs, literal placeholders,
  ANSI palette, and bilingual help. Python-specific help has separate message keys.
- `tests/`: pytest and isolated console smoke test; CI keeps the Bash job and adds Python.

Reference lookup preserves Bash's alphabetical profile traversal, checking name, slot,
alias, then email within each directory (so an earlier alias can shadow a later name).
Imports preserve the Bash behavior of ignoring archived mappings. Python additionally
rejects unsafe archive entries and path-like/hidden profile names, and makes every
profile file mode 600. `run` restores the previous CLI profile in a finally block;
API-key runs exec `agent` directly. `update` uses `uv tool upgrade cursorswap`.
TUI/menubar are now feasible but not implemented; quota-based auto-switch remains absent.

### Legacy files and self-update compatibility

- `cursorswap` — the Bash behavioral specification and legacy tool. The implementation
  notes below retain its original function names; Python equivalents are listed above.
- `cursor-swap` (no `w`, has the hyphen) — the tool's old name before a rename. Kept
  forever as a tiny forwarding shim, **not** because it's still in use: an existing user's
  installed `cursor-swap` runs its own `update` command, which fetches this exact path from
  GitHub and overwrites itself with whatever's there. Deleting this file would break every
  pre-rename install's self-update. It downloads `cursorswap` next to itself (once) and
  execs into it.
- `install.sh` — the one-line installer users pipe from GitHub raw. Installs uv if missing,
  then `uv tool install --force` the Python package (the checkout itself when run from one,
  else `git+` main; `--force` replaces an old Bash `cursorswap`), plus the `cursor-swap`
  shim. Optional arg = bin dir (`UV_TOOL_BIN_DIR`). Same command installs and updates.

### bash-3.2 compatibility guard (top of `cursorswap`, before `set -euo pipefail`)

macOS ships bash 3.2 as `/bin/bash` (frozen there since ~2007 over GPLv3 licensing), which
lacks associative arrays. The script needs them for i18n. The guard block re-execs into a
newer bash if `/opt/homebrew/bin/bash`, `/usr/local/bin/bash`, or `command -v bash` resolves
to one, or exits with an actionable error if none is found. This block must stay written in
bash-3.2-safe syntax (no arrays, no `${var,,}`, etc.) since it has to run correctly *under*
3.2 before deciding whether to escape it.

### Two independent, undocumented auth surfaces

- **CLI session** — `agent login`'s token lives in the macOS Keychain as two items,
  `cursor-access-token` / `cursor-refresh-token` (account `cursor-user`), confirmed by
  reading the actual `cursor-agent` CLI bundle (see CONTRIBUTING.md). `capture_session()` /
  `_restore_session()` snapshot and restore these plus cached `authInfo` in
  `~/.cursor/cli-config.json`.
- **IDE session** — Cursor.app (the desktop editor) has a **separate** login, not in the
  Keychain at all: two plaintext rows, `cursorAuth/accessToken` / `cursorAuth/refreshToken`,
  in the app's own sqlite db (`~/Library/Application Support/Cursor/User/globalStorage/
  state.vscdb`, table `ItemTable`). Found by inspection, not documented anywhere.
  `cmd_ide_add()` / `_restore_ide_session()` handle this side; swapping requires the app
  fully quit first (`_do_ide_switch()` handles the quit/write/relaunch dance), since it only
  reads auth off disk at startup.
- A profile can have either, both, or (for `api-key` type) neither. `cmd_add()` tries to
  capture both and only errors if neither is logged in. `_switch_profile()` is the shared
  entry point that does "whichever this profile has" for both `switch <ref>` and rotating
  `switch`.

### Profile store

`~/.cursor-accounts/<name>/` (path overridable via `CURSOR_SWAP_STORE`, added for safe
testing). Each profile dir has a `meta.json` (`email`, `slot`, `alias`, `type` —
`session`/`api-key`/`ide-only`, `enabled`, optionally `ide_email`) plus whichever of
`access-token`/`refresh-token`/`cli-config.json` (CLI), `ide-auth.json` (IDE), or `api-key`
(API key) applies. `mappings.json` (directory → profile name) lives alongside the profile
dirs, not inside one.

Access tokens can go stale on a currently-*active* profile even while still logged in
(Cursor rotates them silently) — `_effective_access_token()` therefore prefers the live
Keychain/sqlite token over the snapshot whenever the profile in question is the currently
active one, falling back to the snapshot otherwise.

### Usage % (also undocumented)

`agent status`/`agent about` expose no quota info, but the CLI's own JS bundle calls a
backend RPC, `aiserver.v1.DashboardService/GetCurrentPeriodUsage`, with the same bearer
token this tool already has. `usage_summary()` calls it best-effort — no stability
guarantee, and no caller treats failure as fatal (only `cursorswap usage <ref>`, where the
lookup *is* the whole command, exits non-zero).

On failure `usage_summary()` prints a short localized reason and returns 1; `_usage_field()`
wraps it so display sites show that reason, muted, in place of the %. It used to collapse
every failure into a silent `return 1` that rendered as a blank line, which made "session
revoked" indistinguishable from "network blip" — the bug report that prompted this. Branches:
no token, curl failure, HTTP 401/403, other HTTP, and 200-with-unexpected-shape.

The 401/403 message says "session rejected", not "revoked", on purpose: a token that was
never valid lands in the same bucket, so the stronger causal claim would sometimes be wrong.

**Saved IDE session tokens get revoked server-side long before their JWT `exp`** — a stale
snapshot returns HTTP 401 `{"code":"unauthenticated", ..., "error":"ERROR_NOT_LOGGED_IN"}`
while its `exp` claim is still ~2 months out, so expiry checks won't predict it. The
currently-active profile is unaffected because `_effective_access_token()` reads the live
Keychain/sqlite token for it.

Causes, from reading Cursor.app 3.25.9's `out/vs/workbench/workbench.desktop.main.js` (auth
service, `_performAccessTokenRefresh` / `logout` / `revokeCursorSession`):

- **Silent refresh rotation.** The IDE *does* refresh: `POST {backendUrl}/oauth/token` with
  `{grant_type:"refresh_token", client_id:<cursorCreds.authClientId>, refresh_token}` once
  the JWT is within `U8m = 1272h` (~53 days) of `exp` — i.e. roughly a week after issue, not
  after capture (which is why 15h-old snapshots still matched). It stores the response's
  `access_token` under *both* keys, which is why they're byte-identical. The old token is then
  likely rejected. `_ide_save_back()` (called in `_do_ide_switch()` before restoring) re-
  snapshots the outgoing account's live rows into the profile with the same JWT `sub`, so a
  rotated token is captured instead of lost.
- **IDE "Log out" revokes server-side.** `logout()` → `revokeCursorSession()` →
  `POST {backendUrl}/auth/logout` with the bearer token. Logging out in the IDE to switch
  accounts by hand kills that account's saved snapshot; only a re-login + `ide-add` fixes it.

`_restore_ide_session()` deletes all `cursorAuth/*` rows (except BYOK provider keys) before
inserting the snapshot, in one `sqlite3 -bail` transaction, so the previous account's
`cachedTeam`/`teamId`/`stripe*` rows don't leak into the next one. `CURSOR_SWAP_IDE_DB`
overrides the db path for testing — and since `_do_ide_switch()` will really quit a running
Cursor.app, shim `pgrep` to `exit 1` in `PATH` when testing while the app is open.

### i18n

`CURSOR_SWAP_LANG` env var / `-l`/`--lang` flag, English or Vietnamese. `_t(key, ...args)`
looks up `MSG_EN`/`MSG_VI` associative arrays and substitutes `{1}`/`{2}`/... placeholders
via bash parameter substitution — **not** `printf` %-specifiers, because many messages
contain a literal `%` (e.g. "usage %") that a format string would misparse as a conversion
spec. `_t()` always falls back to English, then to the raw key, never to empty — a missed
translation degrades to readable text instead of a blank line or (under `set -e`) a dead
script. `_t()` intentionally prints with no trailing newline (it's used inline mid-line, not
just for full messages), so the correct call pattern for a standalone line is `echo "$(_t
key)"`, not `_t key` alone — `.shellcheckrc` disables the resulting SC2005 warning
project-wide with an explanation.

### Colors

`_accent`/`_muted`/`_bold`/`_bold_accent`/`_sev_pct` wrap text in ANSI codes, off
automatically when stdout isn't a tty and respecting `NO_COLOR`/`FORCE_COLOR` (same
convention as `claude-swap`'s CLI printer, which this project was originally inspired by).
In `cmd_list`'s fixed-width columns, plain text is padded via `printf '%-Ns'` **before**
being wrapped in color — ANSI escape codes count toward printf's field width and would
misalign the table otherwise.

### `set -e` footguns — this exact bug class has bitten the script repeatedly

Every one of these died silently under `set -euo pipefail` instead of hitting the intended
error handling: a bare `((x++))` when `x` is 0 (post-increment evaluates to the old value,
which is falsy); a `grep | cut` piped into a bare command substitution; and six separate
`var=$(sqlite3 ... 2>/dev/null)` calls that would kill the whole script if sqlite3 ever
failed for a reason other than "file missing" (locked, corrupted). Any new
`sqlite3`/`grep`/`jq` call assigned to a variable outside an `if`/`while`/`&&` context needs
a `|| true` (or equivalent) if a plausible failure should degrade gracefully rather than end
the process — check for this pattern specifically before adding new state-reading code.

### CI can sit "queued" for a long time — that's not a script problem

GitHub's hosted macOS runners (`macos-latest`) have had real queue congestion on this repo —
a `workflow_dispatch` run once sat queued for ~1 hour and failed with "the job was not
acquired by Runner... after multiple attempts." That's GitHub-side capacity, not something
to debug in the workflow file. Trust a clean local `bash -n` + `shellcheck` + manual smoke
test (the exact commands in `.github/workflows/ci.yml`'s smoke-test step) over waiting on a
stuck run.

### Dispatch

Python `cli.main()` strips global flags (`-y`/`--yes`, `--force`, `-l`/`--lang`,
`--lang=`) throughout argv, matching Bash even after `--`, then dispatches to `CLI.cmd_*`.
Expected errors go to stderr with exit 1. The legacy Bash script retains its bottom-level
case dispatch. Keep `cursorswap`, `cursor-swap`, and `install.sh` compatible with their
exact GitHub raw paths: old installs depend on them for self-update.
