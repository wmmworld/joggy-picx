from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# Codex: request payload สำหรับสร้าง event ใหม่ (admin only)
class EventCreate(BaseModel):
    organizer_id: uuid.UUID
    name: str = Field(min_length=1, max_length=255)
    start_at: datetime
    end_at: datetime
    allowed_origins: dict | None = None


# Codex: request payload สำหรับเปลี่ยนสถานะ event ตาม transition ที่กำหนด
class EventStatusUpdate(BaseModel):
    status: str


# Codex: response ของ checkpoint ใน event detail
class CheckpointOut(BaseModel):
    id: uuid.UUID
    event_id: uuid.UUID
    name: str
    kind: str
    lat: float | None = None
    lng: float | None = None
    seq_order: int


# Codex: response หลักของ event สำหรับ list/detail
class EventOut(BaseModel):
    id: uuid.UUID
    organizer_id: uuid.UUID
    name: str
    start_at: datetime
    end_at: datetime
    status: str
    allowed_origins: dict | None = None
    retention_until: datetime | None = None
    created_at: datetime
    checkpoints: list[CheckpointOut] = Field(default_factory=list)


# Codex: request payload สำหรับออก partner API key
class PartnerKeyCreate(BaseModel):
    scopes: list[str] = Field(default_factory=lambda: ["public:photos:read"])
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)


# Codex: response ของการ issue key (plaintext แสดงครั้งเดียว)
class PartnerKeyOut(BaseModel):
    key_id: uuid.UUID
    key_prefix: str
    plaintext_key: str
    scopes: list[str]
    rate_limit_per_minute: int
    created_at: datetime
