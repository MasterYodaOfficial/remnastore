#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/test.sh api   Run API tests through uv
  scripts/test.sh bot   Run bot tests through uv
  scripts/test.sh all   Run all Python tests through uv

Examples:
  scripts/test.sh bot
  scripts/test.sh api
  scripts/test.sh all
EOF
}

target="${1:-all}"

run_api() {
  PYTHONPATH=apps/api uv run --no-sync python -m unittest discover -s apps/api/tests -p 'test_*.py'
}

run_bot() {
  PYTHONPATH=apps/bot uv run --no-sync python -m unittest discover -s apps/bot/tests -p 'test_*.py'
}

case "$target" in
  api)
    run_api
    ;;
  bot)
    run_bot
    ;;
  all)
    run_api
    run_bot
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown target: $target" >&2
    echo >&2
    usage >&2
    exit 1
    ;;
esac
