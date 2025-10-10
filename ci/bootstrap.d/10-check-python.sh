#!/usr/bin/env bash
set -euo pipefail

action="${1:-check}"

has_py(){ command -v python3 >/dev/null 2>&1 || command -v python >/dev/null 2>&1; }

case "$action" in
  check)
    if has_py; then
      echo "[OK] Python available: $(python3 --version 2>/dev/null || python --version 2>/dev/null)"
      exit 0
    else
      echo "[ERR] Python 3 not found in PATH" >&2
      echo "      Install Python 3.11+ via your system package manager"
      exit 1
    fi
    ;;
  install)
    # Intentionally commented; enable per-environment if desired.
    # if command -v apt >/dev/null 2>&1; then sudo apt update && sudo apt install -y python3; fi
    # if command -v dnf >/dev/null 2>&1; then sudo dnf install -y python3; fi
    # if command -v brew >/dev/null 2>&1; then brew install python; fi
    ;;
  *)
    echo "[ERR] Unknown action: $action (expected: check|install)" >&2
    exit 2
    ;;
esac


