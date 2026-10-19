# Contributing

## Development and verification

The main implementation is the stdlib-only Python package in `src/cursorswap`, built
with hatchling and managed with uv. Python 3.12+ is required. Run `uv sync`,
`uv run pytest`, and `bash tests/smoke.sh uv run cursorswap`. The tests isolate HOME,
`CURSOR_SWAP_STORE`, and `CURSOR_SWAP_IDE_DB`, and mock all Keychain/app/agent calls.
Never use real account data or quit the running Cursor.app during tests.

Keep the original Bash files compatible for legacy self-update clients. Run
`bash -n` on each shell file and `shellcheck cursorswap cursor-swap install.sh tests/smoke.sh`.
Do not add Python runtime dependencies for work that the standard library can handle.

## Linux / Windows support (help wanted)

`cursorswap` currently only supports macOS. Not because Linux/Windows are hard to script for,
but because we don't actually know how `cursor-agent` stores credentials on those platforms.

On macOS, we confirmed by inspecting the actual CLI bundle
(`~/.local/share/cursor-agent/versions/*/index.js`) that it shells out to
`/usr/bin/security add-generic-password` / `find-generic-password`, storing two Keychain items:

```
service: cursor-access-token   account: cursor-user
service: cursor-refresh-token  account: cursor-user
```

`cursorswap`'s macOS backend (`capture` / `restore` in `src/cursorswap/cli_session.py`) reads
and writes exactly those two items. That's it — no guessing involved, we read the code that
does it.

For Linux and Windows we have no equivalent. The macOS build is platform-specific
(`*.darwin-arm64.node` native modules) — a Linux or Windows install of `cursor-agent` is a
different bundle with potentially a completely different storage mechanism. Guessing wrong
here is worse than not supporting the platform at all: a backend that writes to the wrong
store will report success while silently doing nothing, because `agent` keeps reading from
wherever it actually stores tokens.

**If you have a Linux or Windows machine with `cursor-agent` installed, here's how to find
the real answer:**

### Linux

1. Run `agent login` to get a known-good session.
2. Check the obvious candidates first:
   - `secret-tool search --all cursor-user 2>&1` (Secret Service / libsecret — gnome-keyring, kwallet)
   - `find ~/.config ~/.local/share -iname '*cursor*' -newer /tmp 2>/dev/null` for anything
     written around login time (a plaintext credentials file is a real possibility if no
     keyring daemon is assumed)
3. If you find it, confirm you can round-trip: log out, restore the value you captured, log
   back in without the browser flow, and see `agent status` reflect the account you expect.
4. Open a PR adding a verified Linux credential backend — see "Where to plug in"
   below.

### Windows

Same approach, but check:
- Windows Credential Manager (`cmdkey /list`, or the `CredentialManager` PowerShell module,
  or raw `CredEnumerate`/`CredRead` via a small P/Invoke)
- `%APPDATA%\Cursor` / `%LOCALAPPDATA%\cursor-agent` for a plaintext fallback

The command layer is now Python and can run on Windows, but credential storage, config
paths, and IDE process control remain macOS-specific. A portable runtime alone does not
make the authentication backend portable; verify the native storage before adding support.

### Where to plug in

The Python package funnels CLI credential access through `src/cursorswap/cli_session.py`:

- `secret_get()` / `capture()` — reads the two Keychain items into a saved profile
- `restore()` — writes a saved profile's values back

These currently call `security` directly. A port needs verified platform-specific
credential reads/writes and must make the `~/.cursor/cli-config.json`
path resolution based on the actual per-OS config location `cursor-agent` uses (may not be
`$HOME/.cursor` outside macOS — check with `agent status` after changing `$HOME`/`%APPDATA%`
if you're testing this).

Please include in the PR description exactly how you verified the storage location (command
output, not just "it worked once") — same bar as the macOS backend above.
