#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

usage() {
  cat <<'EOF'
Usage:
  scripts/pr-check.sh [target ...] [options]

Targets:
  python   Run the Python CI job locally
  web      Run the web CI job locally
  admin    Run the admin CI job locally
  all      Run all CI jobs locally (default)

Options:
  --install             Install missing dependencies before running checks
  --install-playwright  Install Playwright Chromium before e2e checks
  --ci-playwright-deps  Install Playwright Chromium with system deps
  -h, --help            Show this help

Examples:
  ./scripts/pr-check.sh
  ./scripts/pr-check.sh python
  ./scripts/pr-check.sh web admin --install
  ./scripts/pr-check.sh all --install --install-playwright
EOF
}

log_section() {
  printf '\n==> %s\n' "$1"
}

run_cmd() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 1
  fi
}

needs_python_install() {
  [[ ! -x "$repo_root/.venv/bin/python" ]]
}

install_python_deps() {
  log_section "Installing Python dependencies"
  run_cmd uv sync --frozen --group dev
}

install_node_deps() {
  local app_dir="$1"
  local app_name="$2"

  log_section "Installing ${app_name} dependencies"
  (
    cd "$repo_root/$app_dir"
    run_cmd npm ci
  )
}

install_playwright_browser() {
  local app_dir="$1"
  local app_name="$2"
  local install_command=(npx playwright install chromium)

  if [[ "$ci_playwright_deps" == true ]]; then
    install_command=(npx playwright install --with-deps chromium)
  fi

  log_section "Installing Playwright Chromium for ${app_name}"
  (
    cd "$repo_root/$app_dir"
    run_cmd "${install_command[@]}"
  )
}

run_python_checks() {
  require_command uv

  if [[ "$install_deps" == true ]] || needs_python_install; then
    install_python_deps
  fi

  log_section "Python: ruff check"
  run_cmd env DATABASE_URL=sqlite+aiosqlite:///./ci-python-quality.sqlite3 \
    uv run --group dev ruff check apps/api apps/bot common scripts

  log_section "Python: ruff format check"
  run_cmd env DATABASE_URL=sqlite+aiosqlite:///./ci-python-quality.sqlite3 \
    uv run --group dev ruff format --check apps/api apps/bot common scripts

  log_section "Python: tests"
  run_cmd env DATABASE_URL=sqlite+aiosqlite:///./ci-python-quality.sqlite3 \
    ./scripts/test.sh all
}

run_frontend_checks() {
  local app_dir="$1"
  local app_name="$2"

  require_command npm
  require_command npx

  if [[ "$install_deps" == true ]] || [[ ! -d "$repo_root/$app_dir/node_modules" ]]; then
    install_node_deps "$app_dir" "$app_name"
  fi

  if [[ "$install_playwright" == true ]]; then
    install_playwright_browser "$app_dir" "$app_name"
  fi

  log_section "${app_name}: lint"
  (
    cd "$repo_root/$app_dir"
    run_cmd npm run lint
  )

  log_section "${app_name}: tests"
  (
    cd "$repo_root/$app_dir"
    run_cmd npm run test
  )

  log_section "${app_name}: typecheck"
  (
    cd "$repo_root/$app_dir"
    run_cmd npm run typecheck
  )

  log_section "${app_name}: browser smoke"
  (
    cd "$repo_root/$app_dir"
    run_cmd npm run test:e2e
  )

  log_section "${app_name}: build"
  (
    cd "$repo_root/$app_dir"
    run_cmd npm run build
  )
}

targets=()
install_deps=false
install_playwright=false
ci_playwright_deps=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    python|web|admin)
      targets+=("$1")
      ;;
    all)
      targets=(python web admin)
      ;;
    --install)
      install_deps=true
      ;;
    --install-playwright)
      install_playwright=true
      ;;
    --ci-playwright-deps)
      install_playwright=true
      ci_playwright_deps=true
      ;;
    -h|--help|help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo >&2
      usage >&2
      exit 1
      ;;
  esac
  shift
done

if [[ ${#targets[@]} -eq 0 ]]; then
  targets=(python web admin)
fi

for target in "${targets[@]}"; do
  case "$target" in
    python)
      run_python_checks
      ;;
    web)
      run_frontend_checks "apps/web" "Web"
      ;;
    admin)
      run_frontend_checks "apps/admin" "Admin"
      ;;
  esac
done

log_section "All requested checks passed"
