#!/usr/bin/env bash
set -euo pipefail

# Local dev helper

docker compose -f ops/docker/compose.yml up --build
