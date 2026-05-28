# apps/backend/joggy/worker/db.py
"""
Worker DB — async session context manager for sync RQ tasks.

RQ workers are sync. Pattern for every worker task:
    def process_something(id: str) -> dict:
        return asyncio.run(_process_something_async(id))

    async def _process_something_async(id: str) -> dict:
        async with worker_db_session() as db:
            ...
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from joggy.core.config import get_settings


@asynccontextmanager
async def worker_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Async DB session for use inside asyncio.run() blocks in RQ worker tasks.
    Creates a fresh engine per call — safe for forked worker processes.
    Auto-commits on success, rolls back on exception.
    """
    engine = create_async_engine(
        get_settings().database_url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Detect stale connections (Supabase idle timeout)
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()
