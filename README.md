# cursorswap

English | [Tiếng Việt](README.vi.md)

Switch the **Cursor IDE** (Cursor.app) between several accounts without logging in again.
macOS only.

## Install / update

```sh
curl -fsSL https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/install.sh | bash
```

Run the same command to update. cursorswap also tells you when a new version is out.

## Add your accounts

```sh
cursorswap add acc1          # 1. save the account Cursor is logged into now
cursorswap logout-local      # 2. sign Cursor out (acc1 stays saved)
                             # 3. log in to the next account in Cursor, wait a few seconds
cursorswap add acc2          # 4. save it
```

Repeat steps 2–4 for more accounts.

## Use

```sh
cursorswap switch            # go to the next account
cursorswap switch acc2       # go to a specific account
cursorswap list              # all accounts + usage %
```

Cursor closes and reopens by itself during a switch.

## Rules

- **Never click "Log out" inside Cursor.** It kills that account's saved session. Use
  `cursorswap logout-local` instead.
- If `list` shows `session rejected` for an account: log in to it in Cursor again, then
  run `cursorswap add <name>`.
- Let a running agent/chat finish before switching - Cursor is closed during the switch.

## What a switch keeps

Only the login changes. These stay as they were:

- chat, composer and agent history
- open windows, projects and tabs
- unsaved files (if Cursor asks to save, the switch is cancelled and nothing changes)
- your own API keys (OpenAI, Claude, ...) set in Cursor

## Other commands

| Command | What it does |
|---|---|
| `cursorswap alias acc2 b` | short name: `cursorswap switch b` |
| `cursorswap disable acc2` / `enable` | skip / include in `switch` |
| `cursorswap remove acc2` | delete a saved account |
| `cursorswap export backup.tar.gz` / `import` | back up / restore (contains tokens - keep it private) |
| `cursorswap --lang vi list` | Vietnamese output |
| `cursorswap help` | everything else |

## Good to know

- Accounts are saved in `~/.cursor-accounts` (only your user can read them).
- Cursor doesn't document how it stores logins, so a Cursor update could break this tool.
- Support for the `cursor-agent` CLI is paused; the old code is on the
  [`archive/cli-support`](https://github.com/CuKhoi/cursor-swap/tree/archive/cli-support) branch.
- Developers: see [CONTRIBUTING.md](CONTRIBUTING.md) and [CLAUDE.md](CLAUDE.md).

## License

MIT - see [LICENSE](LICENSE).
