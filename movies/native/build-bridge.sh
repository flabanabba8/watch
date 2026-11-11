#!/bin/sh
# Explicit user-run source build. No binaries are committed or fetched as releases.
set -eu
# Each child gets only the OS values needed for a public-source build, not profile credentials.
clean() {
  /usr/bin/env -i PATH="$PATH" HOME="${HOME:?HOME is required}" LANG="${LANG:-C.UTF-8}" \
    TMPDIR="${TMPDIR:-/tmp}" GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    GIT_TERMINAL_PROMPT=0 NETRC=/dev/null "$@"
}
output=${1:?Usage: build-bridge.sh /absolute/new-output-directory}
case "$output" in /*) ;; *) printf '%s\n' 'Output must be an absolute path' >&2; exit 1 ;; esac
[ ! -e "$output" ] || { printf '%s\n' 'Output already exists; choose a new directory' >&2; exit 1; }
source_root=$(CDPATH='' cd -- "$(clean dirname -- "$0")" && pwd)
go_bin=${GO_BIN:-go}
command -v "$go_bin" >/dev/null || { printf '%s\n' 'Go 1.26+ is required' >&2; exit 1; }
build_timeout=${HERMES_MOVIES_BUILD_TIMEOUT:-60}
case "$build_timeout" in ''|*[!0-9]*) printf '%s\n' 'Build timeout must be 10–600 seconds' >&2; exit 1 ;; esac
[ "${#build_timeout}" -le 3 ] && [ "$build_timeout" -ge 10 ] && [ "$build_timeout" -le 600 ] || { printf '%s\n' 'Build timeout must be 10–600 seconds' >&2; exit 1; }
build_jobs=${HERMES_MOVIES_BUILD_JOBS:-1}
case "$build_jobs" in 1|2|3|4) ;; *) printf '%s\n' 'Build jobs must be 1–4' >&2; exit 1 ;; esac
revision=0e0abc6bb1c10a02c2d0db2711a04ca9bb836deb
work=$(clean mktemp -d)
trap 'clean rm -rf -- "$work"' EXIT HUP INT TERM
clean git -C "$work" init -q
clean timeout "$build_timeout" git -C "$work" fetch -q --depth=1 https://github.com/DemonKingSwarn/luffy.git "$revision"
clean git -C "$work" checkout -q --detach FETCH_HEAD
[ "$(clean git -C "$work" rev-parse HEAD)" = "$revision" ]
clean python3 "$source_root/make-key-overridable.py" "$work"
clean git -C "$work" apply --check "$source_root/overlay/fallback.patch"
clean git -C "$work" apply "$source_root/overlay/fallback.patch"
clean mkdir -p "$work/cmd/anidroid-bridge"
clean cp "$source_root/"main*.go "$source_root/"public_client*.go "$work/cmd/anidroid-bridge/"
clean cp "$source_root/overlay/"*.go "$work/core/providers/"
cd "$work"
clean timeout "$build_timeout" /usr/bin/env GOTOOLCHAIN=local GOMAXPROCS="$build_jobs" "$go_bin" test -p "$build_jobs" ./core/... ./cmd/anidroid-bridge
clean timeout "$build_timeout" /usr/bin/env GOTOOLCHAIN=local GOMAXPROCS="$build_jobs" CGO_ENABLED=0 "$go_bin" build -p "$build_jobs" -trimpath -buildvcs=false -o "$work/ani-luffy-bridge" ./cmd/anidroid-bridge
clean mkdir -m700 "$output"
if ! clean cp "$work/ani-luffy-bridge" "$output/ani-luffy-bridge"; then
  clean rm -f -- "$output/ani-luffy-bridge"
  clean rmdir -- "$output" 2>/dev/null || true
  exit 1
fi
clean python3 -c 'import hashlib,sys; print("Bridge SHA-256: " + hashlib.file_digest(open(sys.argv[1], "rb"), "sha256").hexdigest())' "$output/ani-luffy-bridge"
printf '%s\n' 'Configure this executable path and SHA-256 in Watch Movies settings.'
