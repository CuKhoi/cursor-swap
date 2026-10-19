#!/usr/bin/env bash
# Pass the console command, e.g. bash tests/smoke.sh uv run cursorswap.
# Runs against a fake Cursor.app db + store in a scratch dir; system commands
# are stubbed so nothing can touch the real app, Keychain or network login.
set -euo pipefail
command=("$@")
scratch=$(mktemp -d "${TMPDIR:-/tmp}/cursorswap-smoke.XXXXXX")
export CURSOR_SWAP_STORE="$scratch/store"
export CURSOR_SWAP_IDE_DB="$scratch/state.vscdb"
export CURSOR_SWAP_YES=1 CURSOR_SWAP_LANG=en NO_COLOR=1 CURSOR_SWAP_NO_UPDATE_CHECK=1
# Keep uv's cache outside the fake HOME, but isolate all Cursor configuration.
export UV_CACHE_DIR="${UV_CACHE_DIR:-${XDG_CACHE_HOME:-$HOME/.cache}/uv}"
export HOME="$scratch/home"
trap 'rm -rf "${scratch:?}"' EXIT
mkdir -p "$HOME" "$scratch/bin"
for tool in security osascript open agent; do
    cat > "$scratch/bin/$tool" <<'STUB'
#!/bin/sh
echo "unexpected system command in smoke test: $0" >&2
exit 99
STUB
    chmod +x "$scratch/bin/$tool"
done
# Cursor.app is never "running" here, so switch never quits/relaunches anything.
printf '#!/bin/sh\nexit 1\n' > "$scratch/bin/pgrep"
chmod +x "$scratch/bin/pgrep"
export PATH="$scratch/bin:$PATH"
cs() { "${command[@]}" "$@"; }

# fake IDE login: unsigned JWT whose payload is {"sub":"auth0|<1>"}
login() {
    local token
    token="h.$(printf '{"sub":"auth0|%s"}' "$1" | base64 | tr '+/' '-_' | tr -d '=').s"
    sqlite3 "$CURSOR_SWAP_IDE_DB" "CREATE TABLE IF NOT EXISTS ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB);
DELETE FROM ItemTable WHERE key LIKE 'cursorAuth/%';
INSERT INTO ItemTable VALUES ('cursorAuth/accessToken','$token'),('cursorAuth/refreshToken','$token'),('cursorAuth/cachedEmail','$1@example.com');"
}
live_email() { sqlite3 "$CURSOR_SWAP_IDE_DB" "SELECT value FROM ItemTable WHERE key='cursorAuth/cachedEmail'"; }

cs --help >/dev/null
cs version
cs --lang vi --help >/dev/null
cs --lang vi lang
cs list
login one
cs add one --alias first
cs logout-local
[[ -z "$(live_email)" ]]
login two
cs add two
cs list | grep -q 'one@example.com'
cs switch first
[[ "$(live_email)" == "one@example.com" ]]
cs switch
[[ "$(live_email)" == "two@example.com" ]]
cs alias | grep -q first
cs disable one
cs enable one
cs renumber
cs export "$scratch/backup.tar.gz"
cs remove one
cs import "$scratch/backup.tar.gz"
cs list | grep -q 'one@example.com'
if out=$(cs login x 2>&1); then
    echo 'archived command unexpectedly succeeded' >&2
    exit 1
fi
echo "$out" | grep -q 'archive/cli-support'
cs purge
echo "smoke test passed"
