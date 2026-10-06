#!/usr/bin/env bash
#  Project:   scalo
#  File:      tools/vendor_patterns.sh
#  Purpose:   Vendor canonical pattern TOMLs from hyperi-ai into pylib's data/
#  Language:  Bash
#
#  License:   Apache-2.0
#  Copyright: (c) 2026 HYPERI PTY LIMITED
#
# Copies the canonical pattern files from a local hyperi-ai checkout:
# runtime patterns into src/scalo/data/, where the runtime loads them, and
# test corpora into tests/fixtures/patterns/, so the wheel does not ship them.
#
# NON-BLOCKING: if hyperi-ai checkout cannot be found, the script
# prints a warning and exits 0. This is intentional — the build /
# install path must continue to work for consumers who don't have
# hyperi-ai checked out (e.g. installing from PyPI).
#
# Checkout discovery (first hit wins):
#   1. $HYPERI_AI_CHECKOUT env var
#   2. ../hyperi-ai (sibling to this project)
#   3. ~/.local/share/hyperi-ai (stealth-mode clone)
#
# Usage:
#   ./tools/vendor_patterns.sh            # vendor all canonical patterns
#   ./tools/vendor_patterns.sh --check    # diff only, exit 1 on drift
#
# See docs/superpowers/specs/2026-05-13-log-scrub-spec.md §3.0 for
# the vendoring-discipline rationale.

set -uo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PYLIB_ROOT=$(dirname "$SCRIPT_DIR")
DATA_DIR="$PYLIB_ROOT/src/scalo/data"
FIXTURES_DIR="$PYLIB_ROOT/tests/fixtures/patterns"
PATTERNS_RELATIVE="standards/patterns"

# Runtime pattern files, loaded by the library. Add as new pattern files land in hyperi-ai.
FILES=(
    "national_ids.toml"
    "gitleaks.toml"
    # Future:
    # "field_names.toml"
)

# Cross-language corpora read only by the parity tests, committed so CI needs no hyperi-ai checkout.
TEST_FILES=(
    "pii_test_fixtures.toml"
    "masking-patterns.yaml"
    "metrics-naming.yaml"
)

CHECK_MODE=false
if [[ "${1:-}" == "--check" ]]; then
    CHECK_MODE=true
fi

# Discover hyperi-ai checkout
find_checkout() {
    local candidates=(
        "${HYPERI_AI_CHECKOUT:-}"
        "$PYLIB_ROOT/../hyperi-ai"
        "$HOME/.local/share/hyperi-ai"
    )
    for path in "${candidates[@]}"; do
        if [[ -n "$path" && -d "$path/$PATTERNS_RELATIVE" ]]; then
            echo "$path"
            return 0
        fi
    done
    return 1
}

warn() {
    # Match scalo's WARN log style for grep-ability
    printf '[WARN] vendor_patterns.sh: %s\n' "$*" >&2
}

info() {
    printf '[INFO] vendor_patterns.sh: %s\n' "$*" >&2
}

if ! checkout=$(find_checkout); then
    warn "no hyperi-ai checkout found — patterns will not be vendored."
    warn "Set HYPERI_AI_CHECKOUT or clone hyperi-ai to one of:"
    warn "    ../hyperi-ai, ~/.local/share/hyperi-ai"
    warn "Skipping (non-blocking)."
    exit 0
fi

info "using hyperi-ai checkout at: $checkout"

mkdir -p "$DATA_DIR" "$FIXTURES_DIR"

drift_count=0
copy_count=0
miss_count=0

targets=()
for file in "${FILES[@]}"; do
    targets+=("$DATA_DIR/$file")
done
for file in "${TEST_FILES[@]}"; do
    targets+=("$FIXTURES_DIR/$file")
done

for dst in "${targets[@]}"; do
    file=$(basename "$dst")
    src="$checkout/$PATTERNS_RELATIVE/$file"

    if [[ ! -f "$src" ]]; then
        warn "missing in hyperi-ai: $src — skipping (non-blocking)"
        miss_count=$((miss_count + 1))
        continue
    fi

    if [[ "$CHECK_MODE" == "true" ]]; then
        if [[ ! -f "$dst" ]] || ! cmp -s "$src" "$dst"; then
            warn "drift detected: $file differs from canonical"
            drift_count=$((drift_count + 1))
        fi
        continue
    fi

    if [[ -f "$dst" ]] && cmp -s "$src" "$dst"; then
        info "$file already in sync"
        continue
    fi

    cp -- "$src" "$dst"
    info "vendored $file"
    copy_count=$((copy_count + 1))
done

if [[ "$CHECK_MODE" == "true" ]]; then
    if [[ "$drift_count" -gt 0 ]]; then
        warn "$drift_count file(s) drift — run tools/vendor_patterns.sh"
        # In check mode we exit non-zero so CI can flag drift, but
        # the warning is the primary signal — operators may choose
        # to suppress this in their CI configuration.
        exit 1
    fi
    info "all vendored patterns match canonical"
    exit 0
fi

info "summary: $copy_count copied, $miss_count missing"
