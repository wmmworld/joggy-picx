"""Tests for DEV-3 watchdog recovery — re-enqueue photos that failed enqueue."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from joggy.db.models import ActorKind, AuditLog
from joggy.worker.recovery import RecoveryResult, reenqueue_pending_photos


# ── Helpers ──────────────────────────────────────────────────────────────────


def _upload_audit(
    photo_id: uuid.UUID | None = None,
    *,
    enqueue_status: str | None = "pending_enqueue",
    created_at: datetime | None = None,
) -> AuditLog:
    """Build an AuditLog row simulating a /ingest/photos upload."""
    context = {"device_id": "pi-001", "job_id": None}
    if enqueue_status is not None:
        context["enqueue_status"] = enqueue_status
    return AuditLog(
        id=uuid.uuid4(),
        actor_kind=ActorKind.photographer,
        action="upload",
        target_kind="photo",
        target_id=photo_id or uuid.uuid4(),
        context=context,
        created_at=(created_at or datetime.utcnow()),
    )


def _mock_db_returning(*query_results: list) -> AsyncMock:
    """Mock AsyncSession.execute returning each call's `query_results` in order.

    Each query_results entry is a list — wraps it as a MagicMock with
    `.scalars().all()` returning the list.
    """
    db = AsyncMock()
    side_effects = []
    for items in query_results:
        scalars_result = MagicMock()
        scalars_result.all.return_value = items
        outer = MagicMock()
        outer.scalars.return_value = scalars_result
        side_effects.append(outer)
    db.execute = AsyncMock(side_effect=side_effects)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


# ── Tests ────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_no_pending_returns_zero():
    """Empty audit log → no work, no commit."""
    db = _mock_db_returning([])  # zero upload rows
    enqueue_fn = MagicMock(return_value="should-not-be-called")

    result = await reenqueue_pending_photos(db, enqueue_fn=enqueue_fn)

    assert result == RecoveryResult(pending_found=0, recovered=0)
    enqueue_fn.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_pending_logs_get_reenqueued():
    """Happy path: pending uploads found → all re-enqueued with new audit rows."""
    pid1, pid2 = uuid.uuid4(), uuid.uuid4()
    pending = [_upload_audit(pid1), _upload_audit(pid2)]
    db = _mock_db_returning(pending, [])  # pending found, none already recovered

    enqueue_fn = MagicMock(side_effect=["job-1", "job-2"])

    result = await reenqueue_pending_photos(db, enqueue_fn=enqueue_fn)

    assert result.pending_found == 2
    assert result.recovered == 2
    assert result.skipped_already_recovered == 0
    assert not result.stopped_redis_still_down

    assert enqueue_fn.call_count == 2
    enqueue_fn.assert_any_call(str(pid1))
    enqueue_fn.assert_any_call(str(pid2))

    # 2 new "enqueue_recovered" audit rows
    assert db.add.call_count == 2
    added = [call.args[0] for call in db.add.call_args_list]
    assert all(row.action == "enqueue_recovered" for row in added)
    assert all(row.actor_kind == ActorKind.system for row in added)
    assert {row.target_id for row in added} == {pid1, pid2}

    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_skip_already_recovered():
    """Photos already marked enqueue_recovered should not be re-enqueued."""
    pid1, pid2 = uuid.uuid4(), uuid.uuid4()
    pending = [_upload_audit(pid1), _upload_audit(pid2)]
    db = _mock_db_returning(pending, [pid1])  # pid1 already recovered

    enqueue_fn = MagicMock(return_value="job-2")

    result = await reenqueue_pending_photos(db, enqueue_fn=enqueue_fn)

    assert result.pending_found == 2
    assert result.recovered == 1
    assert result.skipped_already_recovered == 1

    # Only pid2 was enqueued
    enqueue_fn.assert_called_once_with(str(pid2))


@pytest.mark.asyncio
async def test_stops_on_first_enqueue_failure():
    """If Redis is still down, first failure stops the sweep (don't waste effort)."""
    pid1, pid2, pid3 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    pending = [_upload_audit(pid1), _upload_audit(pid2), _upload_audit(pid3)]
    db = _mock_db_returning(pending, [])

    enqueue_fn = MagicMock(side_effect=ConnectionError("Redis still down"))

    result = await reenqueue_pending_photos(db, enqueue_fn=enqueue_fn)

    assert result.pending_found == 3
    assert result.recovered == 0
    assert result.stopped_redis_still_down is True

    enqueue_fn.assert_called_once_with(str(pid1))
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.asyncio
async def test_filters_out_non_pending_upload_audit_rows():
    """An upload audit with enqueue_status=queued (successful) is not pending — skip."""
    pid_pending = uuid.uuid4()
    pid_queued = uuid.uuid4()
    mixed = [
        _upload_audit(pid_pending, enqueue_status="pending_enqueue"),
        _upload_audit(pid_queued, enqueue_status="queued"),
    ]
    db = _mock_db_returning(mixed, [])

    enqueue_fn = MagicMock(return_value="job-1")

    result = await reenqueue_pending_photos(db, enqueue_fn=enqueue_fn)

    # Only the pending_enqueue one is counted/recovered
    assert result.pending_found == 1
    assert result.recovered == 1
    enqueue_fn.assert_called_once_with(str(pid_pending))


@pytest.mark.asyncio
async def test_filters_out_legacy_upload_without_enqueue_status():
    """Pre-DEV-1 upload audit rows have no enqueue_status field — skip them."""
    pid_legacy = uuid.uuid4()
    pid_pending = uuid.uuid4()
    rows = [
        _upload_audit(pid_legacy, enqueue_status=None),  # no field
        _upload_audit(pid_pending, enqueue_status="pending_enqueue"),
    ]
    db = _mock_db_returning(rows, [])

    enqueue_fn = MagicMock(return_value="job-1")

    result = await reenqueue_pending_photos(db, enqueue_fn=enqueue_fn)

    assert result.pending_found == 1
    enqueue_fn.assert_called_once_with(str(pid_pending))
