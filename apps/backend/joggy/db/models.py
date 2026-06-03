"""
SQLModel database models — Source of Truth สำหรับ schema ทั้งหมด.
อ้างอิง: docs/schema.md (Mermaid ER) — ทุก change ต้องแก้ทั้งไฟล์นี้ + Alembic migration + docs/schema.md
Author: Claude (Tech Lead) — Phase 2 Day 3

⚠️  Security rules (AGENTS.md):
    - face_embeddings = sensitive biometric data — ห้าม return ผ่าน API ใดๆ
    - ห้าม implement runner-facing endpoints
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PG_UUID


def _enum_col(enum_cls, *, nullable: bool = False, default=None):
    """SQLAlchemy column for Python Enum stored as VARCHAR (not native PG ENUM).
    Migration created these columns as TEXT, so native_enum=False is required."""
    return Column(
        SAEnum(enum_cls, native_enum=False, length=32, validate_strings=True),
        nullable=nullable,
        default=default,
    )
from sqlmodel import Field, SQLModel


# ═══════════════════════════════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════════════════════════════

class IntegrationMode(str, Enum):
    pull = "pull"
    push = "push"    # reserved Phase 5+
    embed = "embed"  # reserved Phase 5+


class EventStatus(str, Enum):
    planned = "planned"
    active = "active"
    completed = "completed"
    archived = "archived"


class CheckpointKind(str, Enum):
    start = "start"
    km5 = "km5"
    km10 = "km10"
    finish = "finish"
    other = "other"


class AIReviewStatus(str, Enum):
    auto = "auto"
    manual_pending = "manual_pending"
    manual_approved = "manual_approved"
    manual_rejected = "manual_rejected"


class ReviewQueueStatus(str, Enum):
    pending = "pending"
    in_review = "in_review"
    approved = "approved"
    rejected = "rejected"


class UserRole(str, Enum):
    admin = "admin"
    staff = "staff"


class ActorKind(str, Enum):
    internal_user = "internal_user"
    partner = "partner"
    photographer = "photographer"
    system = "system"


class ErasureStatus(str, Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


# ═══════════════════════════════════════════════════════════════════════════════
# 2.1 Multi-Tenant Core
# ═══════════════════════════════════════════════════════════════════════════════

class Organizer(SQLModel, table=True):
    """Partner / ผู้จัดงาน — 1 organizer มีหลาย event ได้ (D-018)."""

    __tablename__ = "organizers"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True)
    contact_email: str
    integration_mode: IntegrationMode = Field(
        default=IntegrationMode.pull,
        sa_column=_enum_col(IntegrationMode, default=IntegrationMode.pull.value),
    )
    pull_config: Optional[dict] = Field(
        default=None, sa_column=Column(JSONB)
    )
    push_config: Optional[dict] = Field(
        default=None, sa_column=Column(JSONB)
    )  # reserved Phase 5+
    embed_config: Optional[dict] = Field(
        default=None, sa_column=Column(JSONB)
    )  # reserved Phase 5+
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Event(SQLModel, table=True):
    """งานวิ่ง 1 ครั้ง — belongs to 1 organizer."""

    __tablename__ = "events"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organizer_id: uuid.UUID = Field(foreign_key="organizers.id", index=True)
    name: str
    start_at: datetime
    end_at: datetime
    status: EventStatus = Field(
        default=EventStatus.planned,
        sa_column=_enum_col(EventStatus, default=EventStatus.planned.value),
    )
    allowed_origins: Optional[dict] = Field(default=None, sa_column=Column(JSONB))
    retention_until: Optional[datetime] = Field(default=None)  # computed: end_at + 30d
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Checkpoint(SQLModel, table=True):
    """จุดถ่ายรูปในงาน — belongs to 1 event."""

    __tablename__ = "checkpoints"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True)
    name: str
    kind: CheckpointKind = Field(
        default=CheckpointKind.other,
        sa_column=_enum_col(CheckpointKind, default=CheckpointKind.other.value),
    )
    lat: Optional[float] = None
    lng: Optional[float] = None
    seq_order: int = Field(default=0)


# ═══════════════════════════════════════════════════════════════════════════════
# 2.2 Photo & AI Pipeline
# ═══════════════════════════════════════════════════════════════════════════════

class Photo(SQLModel, table=True):
    """รูปต้นฉบับ — 1 row = 1 รูป."""

    __tablename__ = "photos"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True)
    checkpoint_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="checkpoints.id"
    )
    uploaded_by_event_token_id: uuid.UUID = Field(
        foreign_key="event_tokens.id", index=True
    )
    device_id: str = Field(index=True)  # Pi serial หรือ mobile UUID
    r2_key_original: str
    r2_key_thumbnail: Optional[str] = None
    sha256: str = Field(index=True)  # UNIQUE within event_id — กัน duplicate upload
    mime_type: str = Field(default="image/jpeg")
    width: Optional[int] = None
    height: Optional[int] = None
    captured_at: Optional[datetime] = None
    bib_number_nullable: Optional[str] = Field(default=None, index=True)  # ตรงกับ migration column name
    bib_confidence: Optional[float] = None
    gender_nullable: Optional[str] = None  # ตรงกับ migration column name
    gender_confidence: Optional[float] = None
    ai_review_status: AIReviewStatus = Field(
        default=AIReviewStatus.auto,
        sa_column=_enum_col(AIReviewStatus, default=AIReviewStatus.auto.value),
    )
    retention_until: Optional[datetime] = None  # computed: event.end_at + 30d
    created_at: datetime = Field(default_factory=datetime.utcnow)


class FaceEmbedding(SQLModel, table=True):
    """
    Face vector สำหรับ Cross-checkpoint Re-ID (D-014, D-021).

    ⚠️  SECURITY: embedding = sensitive biometric data
        - ห้าม return ผ่าน API ใดๆ (AGENTS.md rule)
        - retention_until = event.end_at + 7d (สั้นกว่ารูป)
        - D-021: ใช้ pgvector ivfflat index สำหรับ ANN search
    """

    __tablename__ = "face_embeddings"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    photo_id: uuid.UUID = Field(foreign_key="photos.id", index=True)
    # Vector(512) — pgvector; index สร้างผ่าน raw SQL ใน Alembic (D-020, D-021)
    embedding: Optional[list] = Field(
        default=None, sa_column=Column(Vector(512))
    )
    face_box_x: Optional[float] = None
    face_box_y: Optional[float] = None
    face_box_w: Optional[float] = None
    face_box_h: Optional[float] = None
    detection_confidence: Optional[float] = None
    retention_until: Optional[datetime] = None  # event.end_at + 7d
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewQueue(SQLModel, table=True):
    """Manual Review — Photo ที่ AI confidence ต่ำ (Phase 3)."""

    __tablename__ = "review_queue"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    photo_id: uuid.UUID = Field(foreign_key="photos.id", unique=True)
    reason: str  # low_ocr_conf | no_bib | ambiguous_face | other
    status: ReviewQueueStatus = Field(
        default=ReviewQueueStatus.pending,
        sa_column=_enum_col(ReviewQueueStatus, default=ReviewQueueStatus.pending.value),
    )
    assigned_to: Optional[uuid.UUID] = Field(
        default=None, foreign_key="app_users.id"
    )
    decision_bib: Optional[str] = None  # human override
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    resolved_at: Optional[datetime] = None


# ═══════════════════════════════════════════════════════════════════════════════
# 2.3 Auth — 3 ชุดแยก (D-017, D-018, D-019)
# ═══════════════════════════════════════════════════════════════════════════════

class EventToken(SQLModel, table=True):
    """
    Per-Event Upload Token — Photographer ใช้ POST /ingest (D-017).
    token_hash = argon2; เก็บ token_prefix (12 chars, L-002) สำหรับ DB lookup + UI.
    """

    __tablename__ = "event_tokens"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True)
    token_hash: str = Field(unique=True)  # argon2 hash
    token_prefix: str  # first 12 chars of plaintext (4 "evt_" + 8 random); L-002
    expires_at: datetime  # = event.end_at
    revoked_at: Optional[datetime] = None
    issued_by_app_user_id: uuid.UUID = Field(foreign_key="app_users.id")
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PartnerApiKey(SQLModel, table=True):
    """Partner API Key — belongs to 1 organizer (D-018)."""

    __tablename__ = "partner_api_keys"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organizer_id: uuid.UUID = Field(foreign_key="organizers.id", index=True)
    key_hash: str = Field(unique=True)  # argon2 hash
    key_prefix: str  # first 8 chars
    scopes: list[str] = Field(
        default_factory=list,
        sa_column=Column(ARRAY(Text())),
    )  # e.g. ["public:photos:read", "erasure:write"]
    rate_limit_per_minute: int = Field(default=60)
    revoked_at: Optional[datetime] = None
    issued_by_app_user_id: uuid.UUID = Field(foreign_key="app_users.id")
    last_used_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppUser(SQLModel, table=True):
    """
    Internal User (admin / staff) — FK ไปยัง Supabase auth.users (D-019).
    ⚠️  MFA บังคับก่อน access dashboard (mfa_enrolled = True)
    """

    __tablename__ = "app_users"

    # PK = FK ไปยัง auth.users(id) ของ Supabase
    id: uuid.UUID = Field(primary_key=True)
    role: UserRole = Field(
        default=UserRole.staff,
        sa_column=_enum_col(UserRole, default=UserRole.staff.value),
    )
    display_name: str
    mfa_enrolled: bool = Field(default=False)
    invited_by: Optional[uuid.UUID] = Field(
        default=None, foreign_key="app_users.id"
    )
    invited_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    last_login_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AppUserOrganizerScope(SQLModel, table=True):
    """Scope table: staff → organizer (many-to-many)."""

    __tablename__ = "app_user_organizer_scope"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    app_user_id: uuid.UUID = Field(foreign_key="app_users.id", index=True)
    organizer_id: uuid.UUID = Field(foreign_key="organizers.id", index=True)


class AppUserEventScope(SQLModel, table=True):
    """Scope table: staff → event (many-to-many)."""

    __tablename__ = "app_user_event_scope"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    app_user_id: uuid.UUID = Field(foreign_key="app_users.id", index=True)
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 2.4 Compliance (D-014)
# ═══════════════════════════════════════════════════════════════════════════════

class ConsentRecord(SQLModel, table=True):
    """Consent ที่ partner ส่งมาตอน register runner เข้า event."""

    __tablename__ = "consent_records"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True)
    bib_number: str = Field(index=True)
    partner_runner_external_id: Optional[str] = None  # id ใน partner's system (ไม่ใช่ PII)
    policy_version: str  # version ของ consent text ที่ runner เห็น
    opt_in_extended_retention: bool = Field(default=False)
    consent_at: datetime
    received_at: datetime = Field(default_factory=datetime.utcnow)


class ErasureRequest(SQLModel, table=True):
    """Right to Erasure — partner POST DELETE /v1/erasure (D-014, SLA 24h)."""

    __tablename__ = "erasure_requests"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: uuid.UUID = Field(foreign_key="events.id", index=True)
    bib_number: str = Field(index=True)
    requested_by_partner_api_key_id: uuid.UUID = Field(
        foreign_key="partner_api_keys.id"
    )
    reason: Optional[str] = None
    status: ErasureStatus = Field(
        default=ErasureStatus.pending,
        sa_column=Column(
            SAEnum(ErasureStatus, native_enum=False, length=32, validate_strings=True),
            nullable=False,
            default=ErasureStatus.pending.value,
            index=True,
        ),
    )
    requested_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    sla_deadline: Optional[datetime] = None  # = requested_at + 24h


class AuditLog(SQLModel, table=True):
    """
    Audit Trail — Polymorphic actor, retention 1 ปี (D-014).
    ใช้ actor_kind เพื่อระบุว่า actor เป็นใคร (1 row = 1 actor เท่านั้น)
    """

    __tablename__ = "audit_logs"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    actor_app_user_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="app_users.id"
    )
    actor_partner_api_key_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="partner_api_keys.id"
    )
    actor_event_token_id: Optional[uuid.UUID] = Field(
        default=None, foreign_key="event_tokens.id"
    )
    actor_kind: ActorKind = Field(sa_column=_enum_col(ActorKind))
    action: str  # upload | delete | erasure | review_approve | key_revoke | ...
    target_kind: str  # photo | event | organizer | face_embedding | ...
    # Claude: DB column is `target_id_nullable` (migration); expose as `target_id` in Python
    target_id: Optional[uuid.UUID] = Field(
        default=None,
        sa_column=Column("target_id_nullable", PG_UUID(as_uuid=True), nullable=True),
    )
    context: Optional[dict] = Field(
        default=None, sa_column=Column(JSONB)
    )  # ip, ua, scope, event_id, etc.
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
