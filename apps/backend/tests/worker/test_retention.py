"""
PDPA Retention Worker Tests — ADR-0004
=======================================

Cron tasks ตาม ADR-0004:
1. delete_expired_photos        — Photo.retention_until < now → R2 + DB + cascade delete
2. delete_expired_face_embeddings — FaceEmbedding.retention_until < now → DB delete
3. anonymize_expired_metadata   — ConsentRecord ที่ photos หายแล้ว → NULL out external_id

Pattern: mock worker_db_session + r2.delete_object (เหมือน test_erasure.py)
Author: Claude (Tech Lead) — Phase 5 PDPA Cron, 2026-06-06
"""
from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from joggy.db.models import (
    ActorKind,
    AuditLog,
    ConsentRecord,
    FaceEmbedding,
    Photo,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _scalars(values):
    """sqlalchemy execute().scalars().all() = values."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


def _make_photo(retention_offset_days: int, *, with_thumbnail: bool = True) -> Photo:
    """Photo ที่หมดอายุไปแล้ว `offset` วัน (ลบ = expired)."""
    photo_id = uuid.uuid4()
    return Photo(
        id=photo_id,
        event_id=uuid.uuid4(),
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-001",
        r2_key_original=f"events/x/{photo_id}/original.jpg",
        r2_key_thumbnail=(
            f"events/x/{photo_id}/thumbnail.jpg" if with_thumbnail else None
        ),
        sha256=uuid.uuid4().hex,
        retention_until=datetime.now(timezone.utc)
        + timedelta(days=retention_offset_days),
    )


def _make_face(retention_offset_days: int) -> FaceEmbedding:
    return FaceEmbedding(
        id=uuid.uuid4(),
        photo_id=uuid.uuid4(),
        retention_until=datetime.now(timezone.utc)
        + timedelta(days=retention_offset_days),
    )


def _captured_audits(db_mock: AsyncMock) -> list[AuditLog]:
    """Pull AuditLog rows out of db.add() call list."""
    return [
        call.args[0]
        for call in db_mock.add.call_args_list
        if isinstance(call.args[0], AuditLog)
    ]


@asynccontextmanager
async def _fake_session(db):
    yield db


def _fresh_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


# ── delete_expired_photos ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_expired_photos_happy_path():
    """Expired photo → R2 delete (original + thumbnail) + DB delete + audit."""
    from joggy.worker.retention import _delete_expired_photos_async

    photo = _make_photo(retention_offset_days=-1)
    db = _fresh_db()
    db.execute.side_effect = [
        _scalars([photo]),  # SELECT Photo WHERE retention_until < now
        MagicMock(),  # DELETE FaceEmbedding WHERE photo_id IN
        MagicMock(),  # DELETE ReviewQueue WHERE photo_id IN
        MagicMock(),  # DELETE PhotoBib WHERE photo_id IN
        MagicMock(),  # DELETE Photo WHERE id IN
    ]

    with (
        patch(
            "joggy.worker.retention.worker_db_session",
            return_value=_fake_session(db),
        ),
        patch("joggy.worker.retention.r2.delete_object") as r2_del,
    ):
        result = await _delete_expired_photos_async()

    assert result["deleted"] == 1
    assert result["failed"] == 0
    # R2: 2 calls (original + thumbnail)
    r2_del.assert_any_call(photo.r2_key_original)
    r2_del.assert_any_call(photo.r2_key_thumbnail)
    assert r2_del.call_count == 2
    # Audit: per-photo (1 photo → 1 audit row)
    audits = _captured_audits(db)
    assert len(audits) == 1
    assert audits[0].actor_kind == ActorKind.system
    assert audits[0].action == "retention_delete_photo"
    assert audits[0].target_kind == "photo"
    assert audits[0].target_id == photo.id


@pytest.mark.asyncio
async def test_delete_expired_photos_skips_non_expired():
    """retention_until in future → not selected (query filter, not code branch)."""
    from joggy.worker.retention import _delete_expired_photos_async

    db = _fresh_db()
    db.execute.side_effect = [_scalars([])]  # empty result set

    with (
        patch(
            "joggy.worker.retention.worker_db_session",
            return_value=_fake_session(db),
        ),
        patch("joggy.worker.retention.r2.delete_object") as r2_del,
    ):
        result = await _delete_expired_photos_async()

    assert result == {"deleted": 0, "failed": 0}
    r2_del.assert_not_called()
    assert _captured_audits(db) == []


@pytest.mark.asyncio
async def test_delete_expired_photos_handles_no_thumbnail():
    """Photo.r2_key_thumbnail = None → R2 called only once (original)."""
    from joggy.worker.retention import _delete_expired_photos_async

    photo = _make_photo(retention_offset_days=-1, with_thumbnail=False)
    db = _fresh_db()
    db.execute.side_effect = [
        _scalars([photo]),
        MagicMock(), MagicMock(), MagicMock(), MagicMock(),
    ]

    with (
        patch(
            "joggy.worker.retention.worker_db_session",
            return_value=_fake_session(db),
        ),
        patch("joggy.worker.retention.r2.delete_object") as r2_del,
    ):
        result = await _delete_expired_photos_async()

    assert result["deleted"] == 1
    assert r2_del.call_count == 1
    r2_del.assert_called_with(photo.r2_key_original)


@pytest.mark.asyncio
async def test_delete_expired_photos_r2_failure_skips_db_delete():
    """
    R2 ลบไม่สำเร็จ → ห้ามลบ DB row (กัน orphan).
    Photo ยังคงอยู่ใน DB → ครั้งถัดมา cron จะ retry.
    Audit log บันทึก failure (action=retention_delete_failed).
    """
    from joggy.worker.retention import _delete_expired_photos_async

    photo = _make_photo(retention_offset_days=-1)
    db = _fresh_db()
    db.execute.side_effect = [_scalars([photo])]

    with (
        patch(
            "joggy.worker.retention.worker_db_session",
            return_value=_fake_session(db),
        ),
        patch(
            "joggy.worker.retention.r2.delete_object",
            side_effect=RuntimeError("r2 down"),
        ),
    ):
        result = await _delete_expired_photos_async()

    assert result["deleted"] == 0
    assert result["failed"] == 1
    # No DELETE Photo query — DB row stays so next run retries
    assert db.execute.call_count == 1  # only SELECT, no DELETE
    audits = _captured_audits(db)
    assert len(audits) == 1
    assert audits[0].action == "retention_delete_failed"
    assert "r2 down" in str(audits[0].context.get("error", ""))


@pytest.mark.asyncio
async def test_delete_expired_photos_per_photo_audit():
    """3 photos expired → 3 audit rows (per-photo granularity per ADR-0004)."""
    from joggy.worker.retention import _delete_expired_photos_async

    photos = [_make_photo(-1) for _ in range(3)]
    db = _fresh_db()
    db.execute.side_effect = [
        _scalars(photos),
        MagicMock(), MagicMock(), MagicMock(), MagicMock(),
    ]

    with (
        patch(
            "joggy.worker.retention.worker_db_session",
            return_value=_fake_session(db),
        ),
        patch("joggy.worker.retention.r2.delete_object"),
    ):
        result = await _delete_expired_photos_async()

    assert result["deleted"] == 3
    audits = _captured_audits(db)
    assert len(audits) == 3
    audit_targets = {a.target_id for a in audits}
    assert audit_targets == {p.id for p in photos}


# ── delete_expired_face_embeddings ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_delete_expired_face_embeddings_happy_path():
    """Expired face embedding → DB delete + audit (biometric data, no R2)."""
    from joggy.worker.retention import _delete_expired_face_embeddings_async

    face = _make_face(retention_offset_days=-1)
    db = _fresh_db()
    db.execute.side_effect = [
        _scalars([face]),
        MagicMock(),  # DELETE FaceEmbedding WHERE id IN
    ]

    with patch(
        "joggy.worker.retention.worker_db_session",
        return_value=_fake_session(db),
    ):
        result = await _delete_expired_face_embeddings_async()

    assert result == {"deleted": 1}
    audits = _captured_audits(db)
    assert len(audits) == 1
    assert audits[0].actor_kind == ActorKind.system
    assert audits[0].action == "retention_delete_face_embedding"
    assert audits[0].target_kind == "face_embedding"
    assert audits[0].target_id == face.id


@pytest.mark.asyncio
async def test_delete_expired_face_embeddings_empty():
    from joggy.worker.retention import _delete_expired_face_embeddings_async

    db = _fresh_db()
    db.execute.side_effect = [_scalars([])]

    with patch(
        "joggy.worker.retention.worker_db_session",
        return_value=_fake_session(db),
    ):
        result = await _delete_expired_face_embeddings_async()

    assert result == {"deleted": 0}
    assert _captured_audits(db) == []


# ── anonymize_expired_metadata ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anonymize_expired_metadata_clears_external_id():
    """
    ConsentRecord ของ event ที่ photos หายแล้ว → set partner_runner_external_id = NULL.
    Keep metadata (bib + event) สำหรับ analytics (ADR-0004 rule).
    """
    from joggy.worker.retention import _anonymize_expired_metadata_async

    consent = ConsentRecord(
        id=uuid.uuid4(),
        event_id=uuid.uuid4(),
        bib_number="4254",
        partner_runner_external_id="ext-12345",
        policy_version="v1",
        consent_at=datetime.now(timezone.utc) - timedelta(days=40),
    )
    db = _fresh_db()
    db.execute.side_effect = [_scalars([consent])]

    with patch(
        "joggy.worker.retention.worker_db_session",
        return_value=_fake_session(db),
    ):
        result = await _anonymize_expired_metadata_async()

    assert result == {"anonymized": 1}
    assert consent.partner_runner_external_id is None
    # Metadata preserved
    assert consent.bib_number == "4254"
    assert consent.event_id is not None
    audits = _captured_audits(db)
    assert len(audits) == 1
    assert audits[0].action == "retention_anonymize_metadata"
    assert audits[0].target_kind == "consent_record"


@pytest.mark.asyncio
async def test_anonymize_skips_already_anonymized():
    """external_id already NULL → query filter excludes it (no-op)."""
    from joggy.worker.retention import _anonymize_expired_metadata_async

    db = _fresh_db()
    db.execute.side_effect = [_scalars([])]

    with patch(
        "joggy.worker.retention.worker_db_session",
        return_value=_fake_session(db),
    ):
        result = await _anonymize_expired_metadata_async()

    assert result == {"anonymized": 0}


# ── Sync RQ entry points ──────────────────────────────────────────────────────


def test_sync_entrypoints_callable():
    """Sync entry points exist for cron CLI invocation."""
    from joggy.worker import retention

    assert callable(retention.delete_expired_photos)
    assert callable(retention.delete_expired_face_embeddings)
    assert callable(retention.anonymize_expired_metadata)
    assert callable(retention.run_all_retention_jobs)
