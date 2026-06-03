"""Security tests for Right-to-Erasure worker behavior."""
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from joggy.db.models import ErasureRequest, ErasureStatus, Photo
from joggy.worker.tasks import _process_erasure_async


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def _scalars_result(values):
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
async def test_erasure_job_fails_when_r2_delete_fails():
    """Do not mark erasure completed if original photo still exists in R2."""
    erasure_id = uuid.uuid4()
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    erasure = ErasureRequest(
        id=erasure_id,
        event_id=event_id,
        bib_number="1234",
        requested_by_partner_api_key_id=uuid.uuid4(),
        status=ErasureStatus.pending,
        sla_deadline=datetime.now(timezone.utc),
    )
    photo = Photo(
        id=photo_id,
        event_id=event_id,
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-001",
        r2_key_original=f"events/{event_id}/{photo_id}/original.jpg",
        sha256="sha",
        bib_number_nullable="1234",
    )
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.execute.side_effect = [
        _scalar_result(erasure),
        _scalars_result([photo]),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    ]

    @asynccontextmanager
    async def _fake_session():
        yield db

    with (
        patch("joggy.worker.tasks.worker_db_session", return_value=_fake_session()),
        patch("joggy.worker.tasks.r2.delete_object", side_effect=RuntimeError("r2 down")),
    ):
        with pytest.raises(RuntimeError):
            await _process_erasure_async(str(erasure_id))

    assert erasure.status != ErasureStatus.completed
