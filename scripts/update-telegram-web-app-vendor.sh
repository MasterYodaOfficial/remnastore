#!/bin/sh
set -eu

ROOT_DIR="$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)"
TARGET_PATH="$ROOT_DIR/apps/web/public/vendor/telegram-web-app.js"
SOURCE_URL="https://telegram.org/js/telegram-web-app.js"

mkdir -p "$(dirname "$TARGET_PATH")"
curl -fsSL "$SOURCE_URL" -o "$TARGET_PATH"
printf 'Updated %s from %s\n' "$TARGET_PATH" "$SOURCE_URL"
