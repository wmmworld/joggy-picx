from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

from joggy.db import models as _models  # noqa: F401

# Codex: Alembic Config object สำหรับเข้าถึงค่าจาก alembic.ini
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Codex: import models แล้วให้ metadata มาจาก SQLModel (D-020 workflow)
target_metadata = SQLModel.metadata


def _database_url() -> str:
    # Codex: อ่าน DATABASE_URL จาก environment เป็นค่า source of truth ของ runtime
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is required for Alembic migrations.")
    return url


def run_migrations_offline() -> None:
    # Codex: โหมด offline สำหรับ generate SQL script โดยไม่ต้องเปิด DB connection
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Codex: central hook ของ Alembic migration context
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)

    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    # Codex: ใช้ async engine ผ่าน asyncpg ตามข้อกำหนด Phase 2
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    import asyncio

    asyncio.run(run_migrations_online())
