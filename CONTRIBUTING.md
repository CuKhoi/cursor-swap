# Contributing

## Development and verification

The tool is the stdlib-only Python package in `src/cursorswap`, built with hatchling and
managed with uv (Python 3.12+). Run `uv sync`, `uv run pytest`, and
`bash tests/smoke.sh uv run cursorswap`. The tests isolate HOME, `CURSOR_SWAP_STORE` and
`CURSOR_SWAP_IDE_DB`, stub `pgrep`/`osascript`/`open`, and block the network. Never use real
account data or quit the running Cursor.app during tests.

Keep the legacy Bash files (`cursorswap`, `cursor-swap`) working for old installs'
self-update. Run `bash -n` on each shell file and
`shellcheck cursorswap cursor-swap install.sh tests/smoke.sh`. Do not add Python runtime
dependencies for work the standard library can handle.

## Scope: Cursor IDE only (for now)

`cursor-agent` CLI support (Keychain sessions, API keys, `run`/`map`) is archived on the
`archive/cli-support` branch. Don't re-add it to `main` piecemeal; when it's revisited it
should come back as a whole, on top of the IDE-only design.

## Linux / Windows support (help wanted)

macOS only, because the IDE session location and app control are only verified there:
the session is plaintext `cursorAuth/*` rows in
`~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` (`ItemTable`), and the
app is quit/relaunched with `osascript` / `open -a Cursor`.

Cursor is a VS Code fork, so on Linux the db is probably
`~/.config/Cursor/User/globalStorage/state.vscdb` and on Windows
`%APPDATA%\Cursor\User\globalStorage\state.vscdb` — but that's unverified. To add a
platform:

1. Log into the IDE, quit it, and confirm the `cursorAuth/accessToken` row is in that db.
2. Confirm a round trip: save the rows, log into another account, write the saved rows
   back with the app quit, start it, and see the first account signed in.
3. Replace the macOS-only pieces in `src/cursorswap/ide.py`: `db_path()`, and
   `running()` / `quit_app()` / `relaunch()` (process check, graceful quit, relaunch).

Please include in the PR exactly how you verified the storage location and round trip
(command output, not just "it worked once").
