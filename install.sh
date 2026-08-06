#!/usr/bin/env bash
# Installer for cursorswap (formerly cursor-swap - see cursor-swap in this
# repo, kept only as a compatibility shim for old installs' self-update).
set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "error: cursorswap only supports macOS (it manages tokens via the macOS Keychain)." >&2
    exit 1
fi

command -v jq >/dev/null || {
    echo "error: jq is required. Install with: brew install jq" >&2
    exit 1
}
command -v agent >/dev/null || echo "warning: cursor-agent CLI ('agent') not found on PATH - install it first: https://cursor.com/cli" >&2

RAW_BASE="https://raw.githubusercontent.com/CuKhoi/cursor-switch/main"
DEST="${1:-$HOME/.local/bin}"
mkdir -p "$DEST"

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || true)"
if [[ -n "$SRC_DIR" && -f "$SRC_DIR/cursorswap" ]]; then
    cp "$SRC_DIR/cursorswap" "$DEST/cursorswap"
else
    curl -fsSL "$RAW_BASE/cursorswap" -o "$DEST/cursorswap"
fi
chmod +x "$DEST/cursorswap"

# also drop the old-name shim, in case muscle memory (or an old doc/bookmark)
# still types "cursor-swap" - it just forwards to cursorswap above.
if [[ -n "$SRC_DIR" && -f "$SRC_DIR/cursor-swap" ]]; then
    cp "$SRC_DIR/cursor-swap" "$DEST/cursor-swap"
else
    curl -fsSL "$RAW_BASE/cursor-swap" -o "$DEST/cursor-swap" 2>/dev/null || true
fi
[[ -f "$DEST/cursor-swap" ]] && chmod +x "$DEST/cursor-swap"

echo "Installed to $DEST/cursorswap"
case ":$PATH:" in
    *":$DEST:"*) ;;
    *) echo "note: $DEST is not on your PATH. Add this to your shell rc file:" ; echo "  export PATH=\"$DEST:\$PATH\"" ;;
esac
echo "Run: cursorswap --help"
