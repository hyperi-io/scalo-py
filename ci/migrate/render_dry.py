#!/usr/bin/env python3
"""Simple helper to dry-render the template using Copier.

Usage:
    python scripts/migrate/render_dry.py /path/to/dest --project-name myproj --package-name myproj

This is a lightweight wrapper to keep CI and local workflows consistent.
"""
import argparse
import subprocess
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dest", help="Destination directory for generated project")
    parser.add_argument("--project-name", default="generated_project")
    parser.add_argument("--package-name", default="generated_project")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    template_dir = Path(__file__).resolve().parents[2] / "template"
    if not template_dir.exists():
        print("Template directory not found:", template_dir, file=sys.stderr)
        sys.exit(2)

    cmd = [
        "copier",
        "copy",
        str(template_dir),
        args.dest,
        "--data",
        f"project_name={args.project_name}",
        "--data",
        f"package_name={args.package_name}",
    ]
    if args.force:
        cmd.append("--force")

    print("Running:", " ".join(cmd))
    subprocess.check_call(cmd)


if __name__ == "__main__":
    main()
