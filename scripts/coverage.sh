#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/coverage.sh api [--html] [--fail-under N]
  scripts/coverage.sh bot [--html] [--fail-under N]
  scripts/coverage.sh all [--html] [--fail-under N]

Examples:
  scripts/coverage.sh api
  scripts/coverage.sh bot --html
  scripts/coverage.sh all --fail-under 30
EOF
}

target="${1:-all}"
if [[ "$target" =~ ^(help|-h|--help)$ ]]; then
  usage
  exit 0
fi

if [[ $# -gt 0 ]]; then
  shift
fi

html_report=false
fail_under=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --html)
      html_report=true
      ;;
    --fail-under)
      shift
      if [[ $# -eq 0 ]]; then
        echo "--fail-under requires a numeric value" >&2
        exit 1
      fi
      fail_under="$1"
      ;;
    help|-h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      echo >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

ensure_dev_dependencies() {
  uv sync --frozen --group dev >/dev/null
}

run_coverage_tests() {
  local data_file="$1"
  local python_path="$2"
  shift 2

  local log_file
  log_file="$(mktemp)"

  if ! COVERAGE_FILE="$data_file" PYTHONPATH="$python_path" uv run --group dev --no-sync "$@" >"$log_file" 2>&1; then
    cat "$log_file" >&2
    rm -f "$log_file"
    return 1
  fi

  rm -f "$log_file"
}

run_report() {
  local data_file="$1"
  local include_path="$2"

  local report_args=(
    python
    -m
    coverage
    report
    --include "$include_path"
  )

  if [[ -n "$fail_under" ]]; then
    report_args+=(
      --fail-under
      "$fail_under"
    )
  fi

  COVERAGE_FILE="$data_file" uv run --group dev --no-sync "${report_args[@]}"
}

run_html() {
  local data_file="$1"
  local output_dir="$2"
  local include_path="$3"

  mkdir -p "$output_dir"
  COVERAGE_FILE="$data_file" uv run --group dev --no-sync python -m coverage html \
    --include "$include_path" \
    -d "$output_dir"
}

run_api() {
  local data_file=".coverage.api"
  rm -f "$data_file"

  run_coverage_tests "$data_file" "apps/api" python -m coverage run \
    --source=app \
    -m unittest discover -s apps/api/tests -p 'test_*.py'

  run_report "$data_file" "apps/api/app/*"

  if [[ "$html_report" == true ]]; then
    run_html "$data_file" ".coverage_html/api" "apps/api/app/*"
  fi
}

run_bot() {
  local data_file=".coverage.bot"
  rm -f "$data_file"

  run_coverage_tests "$data_file" "apps/bot" python -m coverage run \
    --source=bot \
    -m unittest discover -s apps/bot/tests -p 'test_*.py'

  run_report "$data_file" "apps/bot/bot/*"

  if [[ "$html_report" == true ]]; then
    run_html "$data_file" ".coverage_html/bot" "apps/bot/bot/*"
  fi
}

ensure_dev_dependencies

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
  *)
    echo "Unknown target: $target" >&2
    echo >&2
    usage >&2
    exit 1
    ;;
esac
