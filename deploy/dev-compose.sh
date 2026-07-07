#!/usr/bin/env bash
# ============================================================================
# dev-compose.sh — docker compose wrapper for the DEV-server stack.
#
# Pins the isolation flags so the dev stack can never collide with prod:
#   -p polymer-dev            → separate project (own volumes/containers/network)
#   --env-file .env           → dev secrets + INNER_NGINX_PORT/CONF interpolation
#   -f deploy/docker-compose.yml  → the SAME compose the prod stack uses
#
# The dev .env lives at the DEV REPO ROOT ($DEV_REPO/.env) — the same convention
# the prod CI deploy job uses (`cd $REPO && docker compose --env-file .env ...`).
# Both compose's per-service `env_file: ../.env` (resolved relative to deploy/,
# i.e. the repo root) AND `--env-file .env` (relative to CWD, the repo root) read
# that one file, so there is a single source of truth. It must set:
#   COMPOSE_PROJECT_NAME=polymer-dev
#   INNER_NGINX_PORT=8081
#   INNER_NGINX_CONF=nginx.dev-server.behind-proxy.conf
#
# Run from the repo root of the DEV checkout. Examples:
#   deploy/dev-compose.sh up -d postgres redis minio minio-init api worker beat dashboard nginx
#   deploy/dev-compose.sh --profile build run --rm --build webapp-build
#   deploy/dev-compose.sh up -d userbot
#   deploy/dev-compose.sh ps
#   deploy/dev-compose.sh logs -f api
#   deploy/dev-compose.sh down
#
# Override the env-file location if your dev .env lives elsewhere:
#   DEV_ENV_FILE=/some/other/.env deploy/dev-compose.sh ps
# ============================================================================
set -euo pipefail

DEV_ENV_FILE="${DEV_ENV_FILE:-.env}"

if [ ! -f "$DEV_ENV_FILE" ]; then
  echo "dev-compose.sh: env-file not found: $DEV_ENV_FILE" >&2
  echo "  Run from the dev repo root, and create .env from deploy/env.dev-server.example" >&2
  echo "  (chmod 600), or set DEV_ENV_FILE to its path." >&2
  exit 1
fi

exec docker compose \
  --env-file "$DEV_ENV_FILE" \
  -p polymer-dev \
  -f deploy/docker-compose.yml \
  "$@"
