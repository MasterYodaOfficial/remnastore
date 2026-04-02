#!/bin/sh
set -eu

RUNTIME_CONFIG_PATH="${RUNTIME_CONFIG_PATH:-/usr/share/nginx/html/runtime-config.js}"
RUNTIME_CONFIG_GLOBAL="${RUNTIME_CONFIG_GLOBAL:-__REMNASTORE_RUNTIME_CONFIG__}"
RUNTIME_CONFIG_KEYS="${RUNTIME_CONFIG_KEYS:-}"

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g'
}

tmp_path="${RUNTIME_CONFIG_PATH}.tmp"

{
  printf 'window.%s = Object.freeze({' "$RUNTIME_CONFIG_GLOBAL"

  first_entry=1
  for key in $(printf '%s' "$RUNTIME_CONFIG_KEYS" | tr ',' ' '); do
    value="$(printenv "$key" 2>/dev/null || true)"
    escaped_value="$(json_escape "$value")"

    if [ "$first_entry" -eq 1 ]; then
      first_entry=0
      printf '\n'
    else
      printf ',\n'
    fi

    printf '  "%s": "%s"' "$key" "$escaped_value"
  done

  if [ "$first_entry" -eq 0 ]; then
    printf '\n'
  fi

  printf '});\n'
} > "$tmp_path"

mv "$tmp_path" "$RUNTIME_CONFIG_PATH"
