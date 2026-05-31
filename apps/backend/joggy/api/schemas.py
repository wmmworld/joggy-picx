from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


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


# Claude: PATCH payload — full edit (all fields optional). status uses same
# transition validation as EventStatusUpdate.
class EventUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: str | None = None
    allowed_origins: dict | None = None


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


# Phase 4B: Review Queue API schemas

class ReviewQueueItemOut(BaseModel):
    """1 item in the review queue — includes photo metadata + signed thumbnail URL."""
    queue_id: uuid.UUID
    photo_id: uuid.UUID
    reason: str                  # "low_ocr_conf" | "no_bib"
    bib_number: str | None       # AI's best guess (may be None for no_bib)
    bib_confidence: float | None  # 0.0–1.0; None when no bib detected
    thumbnail_url: str | None    # R2 pre-signed URL, expires 1h; None if no thumbnail
    checkpoint_name: str | None  # checkpoint where photo was taken
    created_at: datetime


class ReviewAction(BaseModel):
    """PATCH body — approve or reject a review queue item."""
    action: Literal["approve", "reject"]
    decision_bib: str | None = None  # override bib; ignored when action == "reject"

    @field_validator("decision_bib", mode="before")
    @classmethod
    def _coerce_blank_to_none(cls, v: object) -> object:
        """Coerce empty/whitespace decision_bib to None to prevent storing corrupt bib."""
        if isinstance(v, str) and not v.strip():
            return None
        return v


# Phase 4C: Photo Gallery API schemas

class PhotoItemOut(BaseModel):
    """Single photo item in the gallery response."""
    photo_id: uuid.UUID
    bib_number: str | None        # Photo.bib_number_nullable
    bib_confidence: float | None  # 0.0–1.0 or None when no bib detected
    ai_review_status: Literal["auto", "manual_pending", "manual_approved", "manual_rejected"]
    thumbnail_url: str | None     # R2 signed URL (expires 1h); None if no key available
    checkpoint_name: str | None
    captured_at: datetime | None


class EventPhotosOut(BaseModel):
    """Paginated photo gallery response."""
    items: list[PhotoItemOut]
    total: int = Field(ge=0)         # total matching records
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=100)
    pages: int = Field(ge=1)         # ceil(total / per_page), min 1
