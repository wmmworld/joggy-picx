# Joggy-PicX FastAPI production image
# Author: Claude (Tech Lead) — Phase 5 production deploy, 2026-06-06
# Replaces Codex Phase 1 skeleton

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# System deps: libgomp1 (onnxruntime), libgl1 (opencv-python), curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgomp1 libgl1 libglib2.0-0 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install uv (matches dev tooling per D-010)
RUN pip install --no-cache-dir uv==0.5.18

WORKDIR /app

# ── Dependency layer (cache-friendly) ────────────────────────────────────────
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml
COPY apps/backend/README.md apps/backend/README.md
COPY apps/backend/uv.loc[k] apps/backend/uv.lock* /tmp/_lock_check/

WORKDIR /app/apps/backend
RUN uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# ── App layer ────────────────────────────────────────────────────────────────
WORKDIR /app
COPY apps/backend /app/apps/backend

WORKDIR /app/apps/backend

# Non-root user
RUN useradd --create-home --shell /bin/bash --uid 1000 joggy && \
    chown -R joggy:joggy /app
USER joggy

EXPOSE 8000

# Healthcheck — internal /healthz endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/healthz || exit 1

# 2 uvicorn workers fit in CPX11's 2 GB RAM alongside Redis + worker.
CMD ["uv", "run", "uvicorn", "joggy.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", \
     "--forwarded-allow-ips", "*"]
