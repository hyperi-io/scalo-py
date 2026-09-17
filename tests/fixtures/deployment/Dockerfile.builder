# --- Builder stage (reference; compose before the runtime stage) ---
FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS builder

WORKDIR /app

# Compile bytecode at build time rather than on first import (startup).
ENV UV_COMPILE_BYTECODE=1

# Phase 1: dependency manifests only, so this layer caches independently
# of source changes.
#
# UV_NO_BUILD is set on THIS command only, not as a stage-wide ENV:
# it must cover dependencies (a silent source build is invisible --
# green build, permanently slower service) but NOT the project, which
# is a local source tree with no wheel to install and would fail with
# "marked as --no-build but has no binary distribution". Note uv's
# naming trap: --no-build requires a wheel, --no-binary is the inverse.
COPY pyproject.toml uv.lock ./
RUN UV_NO_BUILD=1 uv sync --frozen --no-dev --no-install-project

# Phase 2: the project itself -- only this layer rebuilds on a source edit.
COPY src/ src/
RUN uv sync --frozen --no-dev
