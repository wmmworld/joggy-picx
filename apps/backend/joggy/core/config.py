"""
Application settings — pydantic-settings v2.
อ่านจาก .env (dev) หรือ environment variables (production / Docker Compose).
Claude (Tech Lead) — Phase 2 Day 3
"""

from functools import lru_cache

from pydantic import model_validator
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
    supabase_jwt_secret: str = ""  # HS256 secret from Supabase → Settings → API → JWT Secret
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

    @model_validator(mode="after")
    def _reject_unsafe_production_secrets(self) -> "Settings":
        # Codex: production ต้อง fail-fast ถ้ายังใช้ placeholder secret จาก dev
        if self.is_production and (
            not self.secret_key
            or self.secret_key == "change-me-in-production"
            or len(self.secret_key) < 32
        ):
            raise ValueError("SECRET_KEY must be set to a strong non-default value in production")
        return self


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton — อ่านครั้งเดียวตอน boot."""
    return Settings()
