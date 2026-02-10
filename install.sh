#!/usr/bin/env bash
# HyperCI Standalone Installation Script
#
# This script adds HyperCI to a project as a git submodule and runs initial bootstrap.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/hyperi-io/hyperci/main/install.sh | bash
#   OR download and run locally:
#   bash install.sh [OPTIONS]
#
# Options:
#   --pin VERSION        Pin to specific semver tag (e.g., --pin v1.2.3)
#   --branch BRANCH      Track specific branch (default: main)
#   --skip-bootstrap     Add submodule but skip initial bootstrap
#   --help               Show this help message
#
# What this script does:
# 1. Checks for git repository
# 2. Adds hyperci as git submodule at ci/
# 3. Runs initial bootstrap (unless --skip-bootstrap)
#
# Requirements:
# - git (for submodule management)
# - Python 3.12+ (for bootstrap)
# - Network access to https://github.com/hyperi-io/hyperci.git

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Defaults
HYPERCI_REPO="https://github.com/hyperi-io/hyperci.git"
HYPERCI_BRANCH="main"
HYPERCI_VERSION=""
SKIP_BOOTSTRAP=false
BOOTSTRAP_ARGS=()

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --pin)
            HYPERCI_VERSION="$2"
            shift 2
            ;;
        --branch)
            HYPERCI_BRANCH="$2"
            shift 2
            ;;
        --skip-bootstrap)
            SKIP_BOOTSTRAP=true
            shift
            ;;
        --help)
            echo "HyperCI Installation Script"
            echo ""
            echo "Usage: $0 [OPTIONS] [BOOTSTRAP_OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --pin VERSION        Pin to specific semver tag (e.g., --pin v1.2.3)"
            echo "  --branch BRANCH      Track specific branch (default: main)"
            echo "  --skip-bootstrap     Add submodule but skip initial bootstrap"
            echo "  --help               Show this help message"
            echo ""
            echo "Bootstrap Options (passed through):"
            echo "  --language LANG      Project language (python, core)"
            echo "  --python-version VER Python version (e.g., 3.13)"
            echo "  --ai                 Run AI setup"
            exit 0
            ;;
        *)
            # Pass unknown arguments to bootstrap
            BOOTSTRAP_ARGS+=("$1")
            shift
            ;;
    esac
done

# Functions
print_header() {
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  HyperCI Installation${NC}"
    echo -e "${BLUE}========================================${NC}"
    echo ""
}

check_requirements() {
    echo -e "${BLUE}[INFO]${NC} Checking requirements..."

    # Check for git
    if ! command -v git &> /dev/null; then
        echo -e "${RED}[ERR]${NC} git is required but not installed"
        echo "       Install git: https://git-scm.com/downloads"
        exit 1
    fi

    # Check for Python 3.12+
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}[ERR]${NC} Python 3.12+ is required but not installed"
        echo "       Install Python: https://www.python.org/downloads/"
        exit 1
    fi

    # Verify Python version
    PYTHON_VERSION=$(python3 --version | awk '{print $2}')
    PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
    PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

    if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 11 ]]; then
        echo -e "${RED}[ERR]${NC} Python 3.12+ required (found $PYTHON_VERSION)"
        exit 1
    fi

    echo -e "${GREEN}[OK]${NC} All requirements met"
}

check_git_repo() {
    echo -e "${BLUE}[INFO]${NC} Checking for git repository..."

    if [[ ! -d .git ]]; then
        echo -e "${RED}[ERR]${NC} Not a git repository"
        echo "       Run: git init"
        exit 1
    fi

    echo -e "${GREEN}[OK]${NC} Git repository found"
}

add_hyperci_submodule() {
    echo -e "${BLUE}[INFO]${NC} Adding HyperCI submodule..."

    # Check if ci/ already exists
    if [[ -e ci ]]; then
        if [[ -d ci/.git ]] || git config --file .gitmodules --get submodule.ci.path &> /dev/null; then
            echo -e "${YELLOW}[WARN]${NC} HyperCI submodule already exists at ci/"
            echo "       To update: cd ci && git pull"
            return 0
        else
            echo -e "${RED}[ERR]${NC} ci/ directory exists but is not a git submodule"
            echo "       Move or remove ci/ directory first"
            exit 1
        fi
    fi

    # Add submodule
    echo -e "${BLUE}[INFO]${NC} Cloning hyperci from $HYPERCI_REPO..."
    git submodule add -b "$HYPERCI_BRANCH" "$HYPERCI_REPO" ci

    # If --pin specified, checkout specific version
    if [[ -n "$HYPERCI_VERSION" ]]; then
        echo -e "${BLUE}[INFO]${NC} Pinning to version: $HYPERCI_VERSION"
        cd ci
        git fetch --tags
        git checkout "$HYPERCI_VERSION"
        cd ..
        git add ci
    fi

    # Initialize submodule
    git submodule update --init ci

    echo -e "${GREEN}[OK]${NC} HyperCI submodule added"

    # Commit submodule addition
    if [[ -n "$HYPERCI_VERSION" ]]; then
        git commit -m "chore: add hyperci submodule (pinned to $HYPERCI_VERSION)" || {
            echo -e "${YELLOW}[WARN]${NC} Could not commit submodule addition"
        }
    else
        git commit -m "chore: add hyperci submodule (tracking $HYPERCI_BRANCH)" || {
            echo -e "${YELLOW}[WARN]${NC} Could not commit submodule addition"
        }
    fi
}

run_bootstrap() {
    if [[ "$SKIP_BOOTSTRAP" == "true" ]]; then
        echo -e "${YELLOW}[INFO]${NC} Skipping bootstrap (--skip-bootstrap specified)"
        echo ""
        echo -e "${BLUE}[INFO]${NC} To bootstrap manually, run:"
        echo "       ./ci/bootstrap install"
        return 0
    fi

    echo -e "${BLUE}[INFO]${NC} Running initial bootstrap..."
    echo ""

    # Run bootstrap (pass through any additional arguments)
    if [[ -x ci/bootstrap ]]; then
        ./ci/bootstrap install "${BOOTSTRAP_ARGS[@]}"
    else
        python3 ci/bootstrap install "${BOOTSTRAP_ARGS[@]}"
    fi

    echo ""
    echo -e "${GREEN}[OK]${NC} Bootstrap complete"
}

print_success() {
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  HyperCI Installation Complete!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Next steps:"
    echo ""
    echo "1. Review generated files:"
    echo "   - .gitignore"
    echo "   - .gitattributes"
    echo "   - ci-local/ (project-specific CI config)"
    echo ""
    echo "2. Configure JFrog credentials in .env:"
    echo "   ARTIFACTORY_USERNAME=your-username"
    echo "   ARTIFACTORY_PASSWORD=your-password"
    echo ""
    echo "3. Run CI checks:"
    echo "   ./ci/run check"
    echo ""
    echo "4. Build your project:"
    echo "   ./ci/run build"
    echo ""
    echo "Documentation: https://github.com/hyperi-io/hyperci"
}

# Main
main() {
    print_header
    check_requirements
    check_git_repo
    add_hyperci_submodule
    run_bootstrap
    print_success
}

main "$@"
