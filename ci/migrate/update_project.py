#!/usr/bin/env python3
"""Run `copier update` for a generated project.

Usage:
    python scripts/migrate/update_project.py /path/to/project

Notes:
- Assumes the project was generated with `copier` and contains copier answers.
- Requires `copier>=9.1.0` installed in the current environment.
"""
import argparse
import subprocess
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("project_dir", help="Path to generated project")
    args = parser.parse_args()

    project = Path(args.project_dir).resolve()
    if not project.exists():
        print("Project directory not found:", project, file=sys.stderr)
        sys.exit(2)

    # Run copier update in-place
    cmd = ["copier", "update", "--force"]
    print("Running:", " ".join(cmd), "in", project)
    subprocess.check_call(cmd, cwd=project)


if __name__ == "__main__":
    main()
