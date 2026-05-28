"""
Application settings — pydantic-settings v2.
อ่านจาก .env (dev) หรือ environment variables (production / Docker Compose).
Claude (Tech Lead) — Phase 2 Day 3
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    secret_key: str = "change-me-in-production"

    # ── Supabase ─────────────────────────────────────────────────────────────
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    database_url: str  # postgresql+asyncpg://...

    # ── Cloudflare R2 ─────────────────────────────────────────────────────────
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket_name: str
    r2_public_base_url: str  # https://pub-xxxx.r2.dev

    # ── Redis ─────────────────────────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — อ่านครั้งเดียวตอน boot."""
    return Settings()
