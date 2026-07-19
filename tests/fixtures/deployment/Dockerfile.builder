# --- Builder stage (reference; compose before the runtime stage) ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Never compile a dependency from source: a silent source build is
# invisible (green build, permanently slower service). Fail instead so
# the missing wheel is dealt with deliberately. Note uv's naming trap --
# --no-build requires a wheel, --no-binary is the inverse.
ENV UV_NO_BUILD=1
# Compile bytecode at build time rather than on first import (startup).
ENV UV_COMPILE_BYTECODE=1

# Phase 1: dependency manifests only, so this layer caches independently
# of source changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Phase 2: the project itself -- only this layer rebuilds on a source edit.
COPY src/ src/
RUN uv sync --frozen --no-dev
