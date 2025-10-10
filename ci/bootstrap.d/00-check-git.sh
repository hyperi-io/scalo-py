#!/usr/bin/env bash
set -euo pipefail

action="${1:-check}"

has_git() { command -v git >/dev/null 2>&1; }

case "$action" in
  check)
    if has_git; then
      echo "[OK] git found: $(git --version)"
      exit 0
    else
      echo "[ERR] git not found in PATH" >&2
      exit 1
    fi
    ;;
  install)
    # NOTE: Installation is intentionally commented out; enable per-environment if desired.
    # echo "[INFO] Attempting to install git (commented out by default)"
    # if command -v apt >/dev/null 2>&1; then sudo apt update && sudo apt install -y git; fi
    # if command -v dnf >/dev/null 2>&1; then sudo dnf install -y git; fi
    # if command -v brew >/dev/null 2>&1; then brew install git; fi
    ;;
  *)
    echo "[ERR] Unknown action: $action (expected: check|install)" >&2
    exit 2
    ;;
esac


