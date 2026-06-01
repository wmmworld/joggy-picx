"""Edge uploader configuration — loaded from .env via pydantic-settings."""
from pydantic import HttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class EdgeSettings(BaseSettings):
    """Settings for the Pi edge uploader daemon.

    Loaded from /home/pi/joggy/.env (when deployed) or .env in working dir.
    Required fields raise ValidationError if missing.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Required ──────────────────────────────────────────────────────────────
    ingest_url: HttpUrl  # e.g. https://vps.joggy.example/ingest/photos
    event_token: str  # Per-event upload token (D-017)

    # ── Identification ────────────────────────────────────────────────────────
    device_id: str = "pi-001"

    # ── Filesystem layout ─────────────────────────────────────────────────────
    inbox_dir: str = "/home/pi/photos/inbox"
    uploaded_dir: str = "/home/pi/photos/uploaded"
    failed_dir: str = "/home/pi/photos/failed"

    # ── Behavior ──────────────────────────────────────────────────────────────
    log_level: str = "INFO"
    request_timeout_seconds: float = 30.0

    # ── Alerting ──────────────────────────────────────────────────────────────
    stuck_alert_threshold: int = 3  # touch marker after N consecutive retries
    stuck_marker_path: str = "/tmp/joggy-edge-stuck"
