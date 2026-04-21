#!/usr/bin/env bash
# OSKAR — Build, tag, and push container images to registry (PRE-10)
#
# Usage:
#   ./scripts/push-image.sh [TAG]
#
# Examples:
#   ./scripts/push-image.sh                   # uses 'latest'
#   ./scripts/push-image.sh v1.0.0            # tags as v1.0.0 AND latest
#
# Environment variables (set in .env or CI/CD):
#   REGISTRY    — e.g. ghcr.io/scanfil-apac  or  scanfilapac.azurecr.io
#   REGISTRY_USER  — for docker login
#   REGISTRY_TOKEN — for docker login (GitHub PAT or ACR password)

set -euo pipefail

TAG="${1:-latest}"
# Harbor registry — hostname confirmed by Manal once VM is provisioned (expected 2026-04-17)
# Update REGISTRY below or set it as an environment variable
REGISTRY="${REGISTRY:-oskar-vm.srxglobal.local}"
APP_IMAGE="${REGISTRY}/oskar-app"
FRONTEND_IMAGE="${REGISTRY}/oskar-frontend"

echo "==> Logging in to ${REGISTRY}"
echo "${REGISTRY_TOKEN}" | docker login "${REGISTRY}" -u "${REGISTRY_USER}" --password-stdin

echo "==> Building oskar-app (backend)"
docker build \
  --file docker/Dockerfile \
  --tag "${APP_IMAGE}:${TAG}" \
  --tag "${APP_IMAGE}:latest" \
  .

echo "==> Building oskar-frontend"
docker build \
  --file frontend/Dockerfile \
  --tag "${FRONTEND_IMAGE}:${TAG}" \
  --tag "${FRONTEND_IMAGE}:latest" \
  ./frontend

echo "==> Pushing oskar-app:${TAG}"
docker push "${APP_IMAGE}:${TAG}"
docker push "${APP_IMAGE}:latest"

echo "==> Pushing oskar-frontend:${TAG}"
docker push "${FRONTEND_IMAGE}:${TAG}"
docker push "${FRONTEND_IMAGE}:latest"

echo "==> Done. Images pushed:"
echo "    ${APP_IMAGE}:${TAG}"
echo "    ${FRONTEND_IMAGE}:${TAG}"
