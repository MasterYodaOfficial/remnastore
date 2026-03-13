#!/usr/bin/env bash
set -euo pipefail

# Local dev helper with bind-mounts and autoreload.

compose_files=(
  -f ops/docker/compose.yml
  -f ops/docker/compose.dev.yml
)

services=(
  api
  bot
  worker
  notifications-worker
  web
  admin
  db
  redis
)

compose() {
  docker compose "${compose_files[@]}" "$@"
}

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
  scripts/dev.sh                         Start all dev services in background
  scripts/dev.sh up [--build] [service] Start all or selected services
  scripts/dev.sh logs [args] [service]  Follow logs for all or selected services
  scripts/dev.sh ps                     Show running services
  scripts/dev.sh restart [service]      Restart all or selected services
  scripts/dev.sh stop [service]         Stop all or selected services
  scripts/dev.sh down [args]            Stop and remove containers
  scripts/dev.sh rebuild [service]      Rebuild and restart all or selected services
  scripts/dev.sh config                 Render merged compose config
  scripts/dev.sh help                   Show this help

Examples:
  scripts/dev.sh
  scripts/dev.sh up --build api
  scripts/dev.sh logs api
  scripts/dev.sh logs --tail=50 web
  scripts/dev.sh restart bot
  scripts/dev.sh stop
  scripts/dev.sh down
  scripts/dev.sh rebuild api web
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
    compose up -d --build "$@"
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
