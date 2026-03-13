#!/bin/sh
set -eu

if [ "$#" -lt 2 ]; then
  echo "Usage: $0 '<command>' <watch-path> [<watch-path>...]" >&2
  exit 1
fi

target="$1"
shift

echo "Starting watcher for: $target"
exec watchfiles --filter python --target-type command "$target" "$@"
