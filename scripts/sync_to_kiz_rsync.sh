#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
REPO_ROOT="$(CDPATH= cd -- "${SCRIPT_DIR}/.." && pwd)"

HOST="${SYNC_HOST:-kiz-rsync}"
REMOTE_DIR="${SYNC_REMOTE_DIR:-~/slurm-tui}"

echo "Syncing ${REPO_ROOT} -> ${HOST}:${REMOTE_DIR}"

ssh "${HOST}" "mkdir -p ${REMOTE_DIR}"

rsync_args=(
  -az
  --delete
  --itemize-changes
  --exclude
  ".git/"
  --exclude
  ".claude/"
  --exclude
  ".idea/"
  --exclude
  ".pytest_cache/"
  --exclude
  ".mypy_cache/"
  --exclude
  ".venv/"
  --exclude
  "__pycache__/"
  --exclude
  "*.pyc"
  --exclude
  ".DS_Store"
)

if (($# > 0)); then
  rsync_args+=("$@")
fi

rsync_args+=("${REPO_ROOT}/" "${HOST}:${REMOTE_DIR}/")

rsync "${rsync_args[@]}"

echo
echo "Remote status after sync:"
ssh "${HOST}" "cd ${REMOTE_DIR} && git status --short"
