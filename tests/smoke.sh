#!/usr/bin/env bash
# Pass the console command, e.g. bash tests/smoke.sh uv run cursorswap.
set -euo pipefail
command=("$@")
scratch=$(mktemp -d "${TMPDIR:-/tmp}/cursorswap-smoke.XXXXXX")
export CURSOR_SWAP_STORE="$scratch/store"
export CURSOR_SWAP_IDE_DB="$scratch/state.vscdb"
export CURSOR_SWAP_YES=1 CURSOR_SWAP_LANG=en NO_COLOR=1
# Keep uv's cache outside the fake HOME, but isolate all Cursor configuration.
export UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/uv}"
export HOME="$scratch/home"
trap 'rm -rf "${scratch:?}"' EXIT
mkdir -p "$HOME" "$scratch/bin"
for tool in security pgrep osascript open agent; do
    cat > "$scratch/bin/$tool" <<'STUB'
#!/bin/sh
echo "unexpected system command in smoke test: $0" >&2
exit 99
STUB
    chmod +x "$scratch/bin/$tool"
done
export PATH="$scratch/bin:$PATH"
cs() { "${command[@]}" "$@"; }

cs --help >/dev/null
cs version
cs --lang vi --help >/dev/null
cs --lang vi lang
cs list
cs add-token sk-ci-test --email ci@example.com --alias ci
cs list | grep -q 'ci@example.com'
cs alias | grep -q ci
if out=$(cs usage ci 2>&1); then
    echo 'usage unexpectedly succeeded for an API key' >&2
    exit 1
fi
echo "$out" | grep -q 'api-key'
cs disable ci
cs enable ci
cs map ci "$scratch"
cs map | grep -q ci
cs unmap "$scratch"
cs renumber
cs export "$scratch/backup.tar.gz"
cs remove ci
cs import "$scratch/backup.tar.gz"
cs list | grep -q 'ci@example.com'
cs remove ci
cs purge
