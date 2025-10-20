#!/usr/bin/env python3
"""
AI Assistant Setup - Thin Wrapper

This bootstrap.d script is a thin wrapper that delegates to /ci/ai tool.

The actual AI setup logic is in /ci/ai (modular ai.d/ scripts).
This wrapper provides backward compatibility with bootstrap integration.

Environment Variables:
    CI_AI_MERGE_MODE=<mode>     # Merge mode: merge, no-overwrite, force, skip

Usage:
    # Via bootstrap (automatic)
    CI_AI_MERGE_MODE=merge ./ci/bootstrap --install

    # Direct (manual - preferred)
    ./ci/ai setup --mode merge
"""

import os
import subprocess
import sys
from pathlib import Path

# Get paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
AI_TOOL = PROJECT_ROOT / "ci" / "ai"


def main() -> int:
    """Main entry point - delegate to /ci/ai tool."""
    if len(sys.argv) < 2:
        print("[ERROR] Usage: 95-ai-settings.py [check|install]")
        return 1

    action = sys.argv[1]

    if action == "check":
        # Verify /ci/ai exists
        if AI_TOOL.exists():
            print("[INFO] /ci/ai tool available")
        else:
            print("[WARN] /ci/ai tool not found")
        return 0

    elif action == "install":
        # Get merge mode from ENV
        merge_mode = os.getenv("CI_AI_MERGE_MODE", "skip")

        if merge_mode == "skip":
            print("[INFO] CI_AI_MERGE_MODE=skip, skipping AI setup")
            return 0

        # Delegate to /ci/ai tool
        print(f"[INFO] Delegating to /ci/ai setup --mode {merge_mode}")
        result = subprocess.run([str(AI_TOOL), "setup", "--mode", merge_mode])
        return result.returncode

    else:
        # Unknown action - skip silently (other scripts may handle it)
        return 0


if __name__ == "__main__":
    sys.exit(main())
