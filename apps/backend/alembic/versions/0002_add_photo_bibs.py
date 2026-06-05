"""add photo_bibs table (ADR-0008 Phase A)

Revision ID: 0002_add_photo_bibs
Revises: 0001_initial_schema
Create Date: 2026-06-05

Context:
    BibDetector.detect_all() (commit e1ac2c5) returns list[BibBox] but the
    DB only had one bib per photo (Photo.bib_number_nullable).  This migration
    adds the photo_bibs 1-to-many table so every runner visible in a group
    photo can be found via bib-number search.

    Phase A is additive-only: photo_bibs is created, the deprecated columns
    on photos are LEFT IN PLACE (they will be DROPped in migration 0003 once
    the API layer has switched over to joining photo_bibs and production is
    verified stable — ADR-0008 Phase C).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_add_photo_bibs"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create photo_bibs table ────────────────────────────────────────────────
    op.create_table(
        "photo_bibs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("photo_id", sa.UUID(), nullable=False),
        sa.Column("bib_number", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("bbox_x1", sa.Integer(), nullable=False),
        sa.Column("bbox_y1", sa.Integer(), nullable=False),
        sa.Column("bbox_x2", sa.Integer(), nullable=False),
        sa.Column("bbox_y2", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["photo_id"],
            ["photos.id"],
            name="fk_photo_bibs_photo_id",
            ondelete="CASCADE",   # ลบรูป → ลบ bib rows อัตโนมัติ
        ),
        sa.PrimaryKeyConstraint("id", name="pk_photo_bibs"),
    )

    # ── Indexes ────────────────────────────────────────────────────────────────
    # photo_id index: JOIN photos ↔ photo_bibs (used in every bib search query)
    op.create_index(
        "ix_photo_bibs_photo_id",
        "photo_bibs",
        ["photo_id"],
    )
    # bib_number index: WHERE photo_bibs.bib_number = :bib (Public API hot path)
    op.create_index(
        "ix_photo_bibs_bib_number",
        "photo_bibs",
        ["bib_number"],
    )


def downgrade() -> None:
    # Drop indexes first, then table (indexes drop automatically on table DROP
    # in Postgres, but being explicit makes downgrade idempotent in edge cases)
    op.drop_index("ix_photo_bibs_bib_number", table_name="photo_bibs")
    op.drop_index("ix_photo_bibs_photo_id", table_name="photo_bibs")
    op.drop_table("photo_bibs")
