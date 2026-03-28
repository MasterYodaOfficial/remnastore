#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

usage() {
  cat <<'EOF'
Usage:
  scripts/install-git-hooks.sh

Configures Git to use the repository hooks from .githooks/.
EOF
}

case "${1:-}" in
  "" )
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

git config core.hooksPath .githooks
chmod +x .githooks/pre-push

echo "Git hooks path configured to .githooks"
