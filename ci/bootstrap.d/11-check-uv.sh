#!/usr/bin/env bash
set -euo pipefail

action="${1:-check}"

case "$action" in
  check)
    if command -v uv >/dev/null 2>&1; then
      echo "[OK] uv found: $(uv --version)"
      exit 0
    else
      echo "[ERR] uv not found in PATH" >&2
      echo "      Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
      exit 1
    fi
    ;;
  install)
    # Intentionally commented; enable per-environment if desired.
    # curl -LsSf https://astral.sh/uv/install.sh | sh
    ;;
  *)
    echo "[ERR] Unknown action: $action (expected: check|install)" >&2
    exit 2
    ;;
esac


