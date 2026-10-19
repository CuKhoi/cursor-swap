#!/usr/bin/env bash
# Installer for cursorswap (the Python package, installed as a uv tool).
#   curl -fsSL https://raw.githubusercontent.com/CuKhoi/cursor-swap/main/install.sh | bash
# Installs uv first if it's missing. An optional first argument overrides the
# bin directory (default: uv's own, ~/.local/bin). Run from a checkout, it
# installs that checkout instead of GitHub main.
set -euo pipefail

if [[ "$(uname)" != "Darwin" ]]; then
    echo "error: cursorswap only supports macOS (it manages tokens via the macOS Keychain)." >&2
    exit 1
fi

REPO="https://github.com/CuKhoi/cursor-swap"
RAW_BASE="https://raw.githubusercontent.com/CuKhoi/cursor-swap/main"

if ! command -v uv >/dev/null; then
    echo "uv not found - installing it (https://docs.astral.sh/uv/)..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    command -v uv >/dev/null || { echo "error: uv install failed - install it manually, then re-run" >&2; exit 1; }
fi

if [[ -n "${1:-}" ]]; then
    mkdir -p "$1"
    UV_TOOL_BIN_DIR="$(cd "$1" && pwd)"
    export UV_TOOL_BIN_DIR
fi

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-}")" 2>/dev/null && pwd || true)"
if [[ -n "$SRC_DIR" && -f "$SRC_DIR/pyproject.toml" ]]; then
    SOURCE="$SRC_DIR"
else
    SOURCE="git+$REPO"
fi

# --force: replaces an older Bash cursorswap at the same path, which uv
# would otherwise refuse to overwrite since it didn't install it.
uv tool install --force --python 3.12 "$SOURCE"

DEST="${UV_TOOL_BIN_DIR:-$(uv tool dir --bin)}"
# also drop the old-name shim, in case muscle memory (or an old doc/bookmark)
# still types "cursor-swap" - it just forwards to cursorswap above.
if [[ -n "$SRC_DIR" && -f "$SRC_DIR/cursor-swap" ]]; then
    cp "$SRC_DIR/cursor-swap" "$DEST/cursor-swap"
else
    curl -fsSL "$RAW_BASE/cursor-swap" -o "$DEST/cursor-swap" 2>/dev/null || true
fi
[[ -f "$DEST/cursor-swap" ]] && chmod +x "$DEST/cursor-swap"

command -v agent >/dev/null || echo "warning: cursor-agent CLI ('agent') not found on PATH - install it first: https://cursor.com/cli" >&2
echo "Installed to $DEST/cursorswap"
case ":$PATH:" in
    *":$DEST:"*) ;;
    *) echo "note: $DEST is not on your PATH. Add this to your shell rc file:" ; echo "  export PATH=\"$DEST:\$PATH\"" ;;
esac
echo "Run: cursorswap --help"
