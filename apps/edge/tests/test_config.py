"""Tests for EdgeSettings — pydantic-settings config loader."""
import os

import pytest
from pydantic import ValidationError

from joggy_edge.config import EdgeSettings


def test_loads_required_fields_from_env(monkeypatch):
    monkeypatch.setenv("INGEST_URL", "https://vps.example/ingest/photos")
    monkeypatch.setenv("EVENT_TOKEN", "evt_test_abc123")
    # Disable .env file loading by changing to empty cwd
    monkeypatch.chdir(os.path.dirname(__file__))
    s = EdgeSettings(_env_file=None)  # type: ignore[call-arg]
    assert str(s.ingest_url).startswith("https://vps.example/")
    assert s.event_token == "evt_test_abc123"
    # Defaults
    assert s.device_id == "pi-001"
    assert s.inbox_dir == "/home/pi/photos/inbox"
    assert s.uploaded_dir == "/home/pi/photos/uploaded"
    assert s.failed_dir == "/home/pi/photos/failed"
    assert s.log_level == "INFO"
    assert s.request_timeout_seconds == 30.0
    assert s.stuck_alert_threshold == 3
    assert s.stuck_marker_path == "/tmp/joggy-edge-stuck"


def test_overrides_defaults_from_env(monkeypatch):
    monkeypatch.setenv("INGEST_URL", "https://vps.example/ingest/photos")
    monkeypatch.setenv("EVENT_TOKEN", "evt_test")
    monkeypatch.setenv("DEVICE_ID", "pi-007")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    s = EdgeSettings(_env_file=None)  # type: ignore[call-arg]
    assert s.device_id == "pi-007"
    assert s.log_level == "DEBUG"


def test_missing_event_token_raises(monkeypatch):
    monkeypatch.delenv("EVENT_TOKEN", raising=False)
    monkeypatch.setenv("INGEST_URL", "https://vps.example/ingest/photos")
    with pytest.raises(ValidationError):
        EdgeSettings(_env_file=None)  # type: ignore[call-arg]


def test_invalid_url_raises(monkeypatch):
    monkeypatch.setenv("INGEST_URL", "not-a-url")
    monkeypatch.setenv("EVENT_TOKEN", "evt_test")
    with pytest.raises(ValidationError):
        EdgeSettings(_env_file=None)  # type: ignore[call-arg]
