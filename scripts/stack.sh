#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

compose() {
  docker compose \
    --env-file "$repo_root/.env" \
    -f ops/docker/compose.yml \
    "$@"
}

services=(
  api
  bot
  worker
  notifications-worker
  broadcast-worker
  web
  admin
  db
  redis
)

is_service() {
  local candidate="${1:-}"
  local service
  for service in "${services[@]}"; do
    if [[ "$service" == "$candidate" ]]; then
      return 0
    fi
  done
  return 1
}

usage() {
  cat <<'EOF'
Usage:
  scripts/stack.sh                         Start all services in background
  scripts/stack.sh up [service]           Start all or selected services
  scripts/stack.sh pull [service]         Pull latest images for all or selected services
  scripts/stack.sh logs [args] [service]  Follow logs for all or selected services
  scripts/stack.sh ps                     Show running services
  scripts/stack.sh restart [service]      Restart all or selected services
  scripts/stack.sh stop [service]         Stop all or selected services
  scripts/stack.sh down [args]            Stop and remove containers
  scripts/stack.sh rebuild [service]      Pull latest images and restart all or selected services
  scripts/stack.sh config                 Render compose config
  scripts/stack.sh help                   Show this help

Examples:
  scripts/stack.sh
  scripts/stack.sh pull
  scripts/stack.sh up api
  scripts/stack.sh logs api
  scripts/stack.sh logs --tail=50 web
  scripts/stack.sh restart bot
  scripts/stack.sh stop
  scripts/stack.sh down
  scripts/stack.sh rebuild api web
EOF
}

command="${1:-up}"

if [[ $# -gt 0 ]]; then
  shift
fi

case "$command" in
  help|-h|--help)
    usage
    ;;
  up)
    compose up -d "$@"
    ;;
  pull)
    compose pull "$@"
    ;;
  logs)
    compose logs --tail=200 -f "$@"
    ;;
  ps)
    compose ps "$@"
    ;;
  restart)
    if [[ $# -eq 0 ]]; then
      compose restart
    else
      compose restart "$@"
    fi
    ;;
  stop)
    if [[ $# -eq 0 ]]; then
      compose stop
    else
      compose stop "$@"
    fi
    ;;
  down)
    compose down "$@"
    ;;
  rebuild)
    compose pull "$@"
    compose up -d "$@"
    ;;
  config)
    compose config "$@"
    ;;
  -*)
    compose up -d "$command" "$@"
    ;;
  *)
    if is_service "$command"; then
      compose up -d "$command" "$@"
    else
      echo "Unknown command: $command" >&2
      echo >&2
      usage >&2
      exit 1
    fi
    ;;
esac
