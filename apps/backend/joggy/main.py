"""
FastAPI application entrypoint — Joggy-PicX Backend.
3 router sets: /ingest (photographer) + /internal (admin/staff) + /v1/public (partner)
Claude (Tech Lead) — Phase 2 Day 3
"""

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from joggy.api import ingest, internal, public
from joggy.core.config import get_settings

settings = get_settings()


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown hooks — Phase 3 เพิ่ม ONNX model preload ที่นี่."""
    # Startup
    # TODO Phase 3: preload ONNX models (yolov8n, paddleocr, buffalo_s)
    yield
    # Shutdown — cleanup ถ้าจำเป็น


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="Joggy-PicX API",
    description="Closed system — Internal use by organizers/staff only. Not runner-facing.",
    version="0.1.0",
    docs_url="/docs" if settings.is_development else None,  # ปิด docs ใน production
    redoc_url=None,
    lifespan=lifespan,
)

# ── CORS — Internal Dashboard Only ────────────────────────────────────────────
# Phase 4: เพิ่ม Vercel production domain
_cors_origins = ["http://localhost:3000"]
if settings.is_production:
    _cors_origins = []  # TODO Phase 4: เพิ่ม https://joggy-picx.vercel.app

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# ── Routers ───────────────────────────────────────────────────────────────────

# Photographer upload (Per-Event Upload Token auth — D-017)
app.include_router(ingest.router, prefix="/ingest", tags=["ingest"])

# Admin / Staff dashboard (Supabase JWT auth — D-019)
app.include_router(internal.router, prefix="/internal", tags=["internal"])

# Partner Pull API (Partner API Key auth — D-018)
app.include_router(public.router, prefix="/v1/public", tags=["public"])


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"], include_in_schema=False)
async def health() -> dict:
    """Health check สำหรับ Docker Compose + Watchtower."""
    return {"status": "ok", "env": settings.app_env, "version": "0.1.0"}
