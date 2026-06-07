"""backfill retention_until for existing photos + face_embeddings

Revision ID: 0003_backfill_retention_until
Revises: 0002_add_photo_bibs
Create Date: 2026-06-06

Context (ADR-0004 PDPA):
    `joggy.worker.retention` cron tasks ใช้ `WHERE retention_until < now()`
    ถ้า row เก่ามี retention_until = NULL → cron จะไม่เจอ → รูปค้างถาวร = PDPA fail.

    Migration นี้ backfill:
    - photos.retention_until        = events.end_at + INTERVAL '30 days'
    - face_embeddings.retention_until = events.end_at + INTERVAL '7 days'
    - events.retention_until         = end_at + INTERVAL '30 days'

    Forward-only (downgrade = no-op): การ "reset" retention_until เป็น NULL
    ไม่มีประโยชน์และเสี่ยง PDPA จึงเลือกไม่ reverse.
"""

from __future__ import annotations

from alembic import op

revision = "0003_backfill_retention_until"
down_revision = "0002_add_photo_bibs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Events: retention_until = end_at + 30d (ถ้า NULL)
    op.execute(
        """
        UPDATE events
        SET retention_until = end_at + INTERVAL '30 days'
        WHERE retention_until IS NULL
        """
    )

    # 2. Photos: retention_until = event.end_at + 30d
    op.execute(
        """
        UPDATE photos
        SET retention_until = events.end_at + INTERVAL '30 days'
        FROM events
        WHERE photos.event_id = events.id
          AND photos.retention_until IS NULL
        """
    )

    # 3. Face embeddings: retention_until = event.end_at + 7d (ตาม ADR-0004 strict)
    op.execute(
        """
        UPDATE face_embeddings AS fe
        SET retention_until = events.end_at + INTERVAL '7 days'
        FROM photos, events
        WHERE fe.photo_id = photos.id
          AND photos.event_id = events.id
          AND fe.retention_until IS NULL
        """
    )

    # 4. Index on retention_until ทุก table — cron queries ใช้บ่อย
    op.create_index(
        "ix_photos_retention_until",
        "photos",
        ["retention_until"],
    )
    op.create_index(
        "ix_face_embeddings_retention_until",
        "face_embeddings",
        ["retention_until"],
    )


def downgrade() -> None:
    # Drop indexes only — ห้าม reset retention_until เป็น NULL (PDPA risk).
    op.drop_index("ix_face_embeddings_retention_until", table_name="face_embeddings")
    op.drop_index("ix_photos_retention_until", table_name="photos")
