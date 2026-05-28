"""initial schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-05-28 16:40:00
"""

from __future__ import annotations

from alembic import op

# Codex: Alembic revision identifiers
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Codex: raw SQL จำเป็นสำหรับ pgvector extension และ ivfflat index ตาม ADR-0007/D-020
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # Codex: core multi-tenant tables
    op.execute(
        """
        CREATE TABLE organizers (
          id UUID PRIMARY KEY,
          name TEXT NOT NULL,
          contact_email TEXT NOT NULL,
          integration_mode TEXT NOT NULL,
          pull_config JSONB,
          push_config JSONB,
          embed_config JSONB,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE events (
          id UUID PRIMARY KEY,
          organizer_id UUID NOT NULL REFERENCES organizers(id) ON DELETE RESTRICT,
          name TEXT NOT NULL,
          start_at TIMESTAMPTZ NOT NULL,
          end_at TIMESTAMPTZ NOT NULL,
          status TEXT NOT NULL,
          allowed_origins JSONB,
          retention_until TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE checkpoints (
          id UUID PRIMARY KEY,
          event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
          name TEXT NOT NULL,
          kind TEXT NOT NULL,
          lat NUMERIC,
          lng NUMERIC,
          seq_order INT
        );
        """
    )
    op.execute(
        """
        CREATE TABLE app_users (
          id UUID PRIMARY KEY,
          role TEXT NOT NULL,
          display_name TEXT,
          mfa_enrolled BOOLEAN NOT NULL DEFAULT false,
          invited_by UUID,
          invited_at TIMESTAMPTZ,
          accepted_at TIMESTAMPTZ,
          last_login_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE event_tokens (
          id UUID PRIMARY KEY,
          event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
          token_hash TEXT NOT NULL UNIQUE,
          token_prefix TEXT NOT NULL,
          expires_at TIMESTAMPTZ NOT NULL,
          revoked_at TIMESTAMPTZ,
          issued_by_app_user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE partner_api_keys (
          id UUID PRIMARY KEY,
          organizer_id UUID NOT NULL REFERENCES organizers(id) ON DELETE CASCADE,
          key_hash TEXT NOT NULL UNIQUE,
          key_prefix TEXT NOT NULL,
          scopes TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
          rate_limit_per_minute INT NOT NULL DEFAULT 60,
          revoked_at TIMESTAMPTZ,
          issued_by_app_user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
          last_used_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute(
        """
        CREATE TABLE photos (
          id UUID PRIMARY KEY,
          event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
          checkpoint_id UUID REFERENCES checkpoints(id) ON DELETE SET NULL,
          uploaded_by_event_token_id UUID REFERENCES event_tokens(id) ON DELETE SET NULL,
          device_id TEXT,
          r2_key_original TEXT NOT NULL,
          r2_key_thumbnail TEXT,
          sha256 TEXT NOT NULL,
          mime_type TEXT NOT NULL,
          width INT,
          height INT,
          captured_at TIMESTAMPTZ,
          bib_number_nullable TEXT,
          bib_confidence NUMERIC,
          gender_nullable TEXT,
          gender_confidence NUMERIC,
          ai_review_status TEXT NOT NULL DEFAULT 'auto',
          retention_until TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          CONSTRAINT photos_event_sha256_unique UNIQUE(event_id, sha256)
        );
        """
    )
    op.execute(
        """
        CREATE TABLE face_embeddings (
          id UUID PRIMARY KEY,
          photo_id UUID NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
          embedding vector(512) NOT NULL,
          face_box_x NUMERIC,
          face_box_y NUMERIC,
          face_box_w NUMERIC,
          face_box_h NUMERIC,
          detection_confidence NUMERIC,
          retention_until TIMESTAMPTZ,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    # Claude: เพิ่ม 3 tables ที่ขาดจาก initial migration
    op.execute(
        """
        CREATE TABLE app_user_organizer_scope (
          id UUID PRIMARY KEY,
          app_user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
          organizer_id UUID NOT NULL REFERENCES organizers(id) ON DELETE CASCADE,
          UNIQUE (app_user_id, organizer_id)
        );
        """
    )
    op.execute("CREATE INDEX app_user_organizer_scope_user_idx ON app_user_organizer_scope(app_user_id);")
    op.execute(
        """
        CREATE TABLE app_user_event_scope (
          id UUID PRIMARY KEY,
          app_user_id UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
          event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
          UNIQUE (app_user_id, event_id)
        );
        """
    )
    op.execute("CREATE INDEX app_user_event_scope_user_idx ON app_user_event_scope(app_user_id);")
    op.execute(
        """
        CREATE TABLE consent_records (
          id UUID PRIMARY KEY,
          event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
          bib_number TEXT NOT NULL,
          partner_runner_external_id TEXT,
          policy_version TEXT NOT NULL,
          opt_in_extended_retention BOOLEAN NOT NULL DEFAULT false,
          consent_at TIMESTAMPTZ NOT NULL,
          received_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )
    op.execute("CREATE INDEX consent_records_event_bib_idx ON consent_records(event_id, bib_number);")

    op.execute(
        """
        CREATE TABLE review_queue (
          id UUID PRIMARY KEY,
          photo_id UUID NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
          reason TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'pending',
          assigned_to UUID REFERENCES app_users(id) ON DELETE SET NULL,
          decision_bib_nullable TEXT,
          notes TEXT,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          resolved_at TIMESTAMPTZ
        );
        """
    )
    op.execute(
        """
        CREATE TABLE erasure_requests (
          id UUID PRIMARY KEY,
          event_id UUID NOT NULL REFERENCES events(id) ON DELETE CASCADE,
          bib_number TEXT NOT NULL,
          requested_by_partner_api_key_id UUID REFERENCES partner_api_keys(id) ON DELETE SET NULL,
          reason TEXT,
          status TEXT NOT NULL DEFAULT 'pending',
          requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          completed_at TIMESTAMPTZ,
          sla_deadline TIMESTAMPTZ
        );
        """
    )
    op.execute(
        """
        CREATE TABLE audit_logs (
          id UUID PRIMARY KEY,
          actor_app_user_id UUID REFERENCES app_users(id) ON DELETE SET NULL,
          actor_partner_api_key_id UUID REFERENCES partner_api_keys(id) ON DELETE SET NULL,
          actor_event_token_id UUID REFERENCES event_tokens(id) ON DELETE SET NULL,
          actor_kind TEXT NOT NULL,
          action TEXT NOT NULL,
          target_kind TEXT NOT NULL,
          target_id_nullable UUID,
          context JSONB,
          created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    # Codex: indexes สำหรับ retention cleanup และ vector search
    op.execute(
        """
        CREATE INDEX face_embeddings_embedding_idx
          ON face_embeddings USING ivfflat (embedding vector_cosine_ops)
          WITH (lists = 100);
        """
    )
    op.execute("CREATE INDEX photos_retention_until_idx ON photos(retention_until);")
    op.execute("CREATE INDEX face_embeddings_retention_until_idx ON face_embeddings(retention_until);")


def downgrade() -> None:
    # Codex: downgrade ลบ index ก่อน แล้วค่อยลบตารางย้อนลำดับ dependency
    op.execute("DROP INDEX IF EXISTS face_embeddings_retention_until_idx;")
    op.execute("DROP INDEX IF EXISTS photos_retention_until_idx;")
    op.execute("DROP INDEX IF EXISTS face_embeddings_embedding_idx;")

    op.execute("DROP TABLE IF EXISTS audit_logs;")
    op.execute("DROP TABLE IF EXISTS erasure_requests;")
    op.execute("DROP TABLE IF EXISTS consent_records;")
    op.execute("DROP TABLE IF EXISTS app_user_event_scope;")
    op.execute("DROP TABLE IF EXISTS app_user_organizer_scope;")
    op.execute("DROP TABLE IF EXISTS review_queue;")
    op.execute("DROP TABLE IF EXISTS face_embeddings;")
    op.execute("DROP TABLE IF EXISTS photos;")
    op.execute("DROP TABLE IF EXISTS partner_api_keys;")
    op.execute("DROP TABLE IF EXISTS event_tokens;")
    op.execute("DROP TABLE IF EXISTS checkpoints;")
    op.execute("DROP TABLE IF EXISTS app_users;")
    op.execute("DROP TABLE IF EXISTS events;")
    op.execute("DROP TABLE IF EXISTS organizers;")
