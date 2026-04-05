#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-fast}"

if [ "$MODE" != "fast" ] && [ "$MODE" != "full" ]; then
  echo "Usage: ./scripts/verify.sh [fast|full]" >&2
  exit 2
fi

if ! command -v pre-commit >/dev/null 2>&1; then
  echo "pre-commit is required. Install with: python -m pip install pre-commit" >&2
  exit 1
fi

if [ "$MODE" = "fast" ]; then
  SKIP=coverage pre-commit run --all-files
  echo "Fast preflight complete. Run ./scripts/verify.sh full before completion."
  exit 0
fi

if [ "$MODE" = "full" ]; then
  pre-commit run --all-files
  exit 0
fi
