#!/usr/bin/env python3
"""
Python Tools Bootstrap

This script ensures Python development tools are available in .venv-ci.

CRITICAL SAFEGUARDS:
- MUST run inside .venv-ci (enforced by bootstrap.py)
- NEVER uses system Python for pip operations
- Can install ANY Python package as needed
- All installations target .venv-ci only
"""

import os
import sys
import subprocess
from pathlib import Path

# Import hyperlib from pip-installed package (installed by bootstrap Phase 1)
from hyperlib import get_logger  # type: ignore


def check_tool(tool_name: str) -> bool:
    """Check if a Python tool is available."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", tool_name, "--version"],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except:
        return False


def install_tool(tool_spec: str, logger) -> bool:
    """
    Install a Python tool using pip.
    
    SAFEGUARD: This MUST be called from within .venv-ci
    The bootstrap.py ensures we're in the venv before calling this.
    """
    # Double-check we're in a venv (belt and suspenders)
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        logger.error("CRITICAL: Not running in a virtual environment!")
        logger.error("This script must be run through bootstrap.py")
        return False
    
    logger.info(f"Installing {tool_spec}")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", tool_spec],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install {tool_spec}: {e}")
        return False


def main() -> int:
    """Main entry point."""
    logger = get_logger("python-tools")
    
    if len(sys.argv) < 2:
        logger.error("Usage: %s [check|install]", sys.argv[0])
        return 1
    
    action = sys.argv[1]
    
    # Core Python tools that should always be available
    core_tools = [
        "pip>=24.0",
        "setuptools>=70.0.0",
        "wheel>=0.42.0",
        "build>=1.0.0",
    ]
    
    # Development tools (installed only with --install)
    dev_tools = [
        "copier>=9.1.0",
        "nox>=2024.0.0",
        "pytest>=8.0.0",
        "ruff>=0.1.0",
        "black>=24.0.0",
        "mypy>=1.8.0",
        "twine>=5.0.0",
        "tomli-w>=1.0.0",  # Required for version sync (pyproject.toml writing)
        "python-semantic-release>=9.0.0",  # Pure Python semantic versioning (replaces Node.js)
        "pip-audit>=2.6.0",
        "bandit[toml]>=1.7.0",
        "safety>=3.0.0",
        "vermin>=1.6.0",
    ]
    
    if action == "check":
        # Just ensure pip is up to date
        logger.info("Python tools check (pip is managed by venv)")
        
        # Verify we're in a venv
        if not os.environ.get("HSF_IN_CI_VENV"):
            logger.warning("Not running in CI venv")
            return 1
        
        return 0
    
    elif action == "install":
        # Install tools if BOOTSTRAP_INSTALL is set
        if os.environ.get("BOOTSTRAP_INSTALL") != "1":
            logger.info("Skipping install (BOOTSTRAP_INSTALL not set)")
            return 0
        
        # Ensure core tools
        for tool in core_tools:
            tool_name = tool.split("[")[0].split(">")[0].split("=")[0]
            if not check_tool(tool_name):
                if not install_tool(tool, logger):
                    return 1
        
        # Install dev tools
        logger.info("Installing Python development tools")
        for tool in dev_tools:
            # Don't fail on individual tool failures
            install_tool(tool, logger)
        
        logger.info("Python tools installation complete")
        return 0
    
    else:
        logger.error("Unknown action: %s", action)
        return 1


if __name__ == "__main__":
    sys.exit(main())
