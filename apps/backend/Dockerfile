# Codex: Dockerfile skeleton สำหรับ FastAPI container (CPU-only base image)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Codex: ติดตั้ง uv ใน container สำหรับ dependency management ตาม D-010
RUN pip install --no-cache-dir uv

# Codex: copy manifests ก่อนเพื่อใช้ Docker layer cache
COPY pyproject.toml uv.lock ./
COPY apps/backend/pyproject.toml apps/backend/pyproject.toml

# Codex: sync dependencies แบบ production-only (ยังไม่มี source runtime จริงใน Phase 1)
RUN uv sync --frozen --package joggy-backend --no-dev || uv sync --package joggy-backend --no-dev

COPY apps/backend apps/backend

EXPOSE 8000

# Codex: placeholder command จนกว่า FastAPI entrypoint จะ implement ใน Phase 2
CMD ["uv", "run", "--package", "joggy-backend", "python", "-c", "print('joggy-backend skeleton ready')"]
