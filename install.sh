#!/usr/bin/env bash
# Installer for cursor-swap.
set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "error: cursor-swap only supports macOS (it manages tokens via the macOS Keychain)." >&2
    exit 1
fi

command -v jq >/dev/null || {
    echo "error: jq is required. Install with: brew install jq" >&2
    exit 1
}
command -v agent >/dev/null || echo "warning: cursor-agent CLI ('agent') not found on PATH - install it first: https://cursor.com/cli" >&2

DEST="${1:-$HOME/.local/bin}"
mkdir -p "$DEST"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$SRC_DIR/cursor-swap" "$DEST/cursor-swap"
chmod +x "$DEST/cursor-swap"

echo "Installed to $DEST/cursor-swap"
case ":$PATH:" in
    *":$DEST:"*) ;;
    *) echo "note: $DEST is not on your PATH. Add this to your shell rc file:" ; echo "  export PATH=\"$DEST:\$PATH\"" ;;
esac
echo "Run: cursor-swap --help"
