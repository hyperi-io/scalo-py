# --- Builder stage (reference; compose before the runtime stage) ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Dependency manifests first so the install layer caches independently
# of source changes.
COPY pyproject.toml uv.lock ./
COPY src/ src/

RUN uv sync --frozen --no-dev
