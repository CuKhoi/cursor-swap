# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`cursorswap` — a single macOS bash script that snapshots and restores multiple Cursor
account logins (both the `cursor-agent` CLI and the Cursor.app desktop IDE), so a user can
switch between accounts without re-authenticating each time. No build step, no package
manager, no runtime dependency beyond the script itself, `jq`, and `sqlite3`/`security`
(both ship with macOS).

## Commands

```bash
# syntax + lint (must both be clean before committing)
bash -n cursorswap cursor-swap install.sh
shellcheck cursorswap cursor-swap install.sh    # brew install shellcheck if missing

# reinstall the local working copy over the installed binary, for manual testing
./install.sh                                     # installs to ~/.local/bin

# run the exact smoke test CI runs, against an isolated store (never touches
# the real ~/.cursor-accounts or Keychain/IDE data)
export CURSOR_SWAP_STORE=/tmp/cswap-test-store CURSOR_SWAP_YES=1
./cursorswap add-token sk-test --email test@example.com --alias t
./cursorswap list
./cursorswap remove t
```

There is no test suite beyond the CI smoke test in `.github/workflows/ci.yml` — this is a
single bash file with no unit-testable internal API. Verification is: syntax check,
shellcheck, then exercising real commands against `CURSOR_SWAP_STORE` pointed at a scratch
directory. **Never test destructive commands (`remove`, `purge`, `switch`, `ide-switch`)
against the real store without `CURSOR_SWAP_STORE` set** — a prior session in this repo
accidentally deleted a real saved profile this way.

CI (`.github/workflows/ci.yml`) runs on `macos-latest` specifically — the tool is
macOS-only and the smoke test exercises real commands, not just static analysis.

## Architecture

### Three files, one is a compatibility shim

- `cursorswap` — the actual tool (~1300 lines). Everything below is about this file.
- `cursor-swap` (no `w`, has the hyphen) — the tool's old name before a rename. Kept
  forever as a tiny forwarding shim, **not** because it's still in use: an existing user's
  installed `cursor-swap` runs its own `update` command, which fetches this exact path from
  GitHub and overwrites itself with whatever's there. Deleting this file would break every
  pre-rename install's self-update. It downloads `cursorswap` next to itself (once) and
  execs into it.
- `install.sh` — installs both of the above to `~/.local/bin` (or an arg-given dir).

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
guarantee, and every caller treats failure as "print nothing," never a hard error.

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

### `set -e` footguns already hit twice — watch for the pattern

This script has been bitten multiple times by constructs that die silently under
`set -euo pipefail` instead of hitting the intended error handling: a bare `((x++))` when
`x` is 0 (post-increment evaluates to the old value, which is falsy), and a bare
`var=$(cmd1 | cmd2)` where `cmd1`/`cmd2` failing (locked file, no match) kills the whole
script instead of falling through to a `die()`/empty-check a few lines down. Any new
`sqlite3`/`grep`/`jq` call assigned to a variable outside an `if`/`while`/`&&` context should
get a `|| true` (or equivalent) if a plausible failure should degrade gracefully rather than
end the process.

### Dispatch

Single `case "${1:-}" in ... esac` at the very bottom maps subcommands to `cmd_*`
functions. Flags (`-y`/`--yes`, `--force`, `-l`/`--lang`) are stripped out of `$@` in a loop
before the dispatch runs.
