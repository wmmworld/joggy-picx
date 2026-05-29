import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from joggy.ai.bib_detector import BibBox
from joggy.ai.bib_ocr import BibResult
from joggy.ai.face_embedder import FaceResult, FaceBox
from joggy.db.models import AIReviewStatus, Photo, Event, ReviewQueueStatus
from joggy.worker.pipeline import run_pipeline, _BIB_CONF_THRESHOLD


def _make_photo(event_id: uuid.UUID) -> Photo:
    return Photo(
        id=uuid.uuid4(),
        event_id=event_id,
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-001",
        r2_key_original="events/e/p/original.jpg",
        sha256="abc123",
    )


def _make_event() -> Event:
    now = datetime.now(timezone.utc)
    return Event(
        id=uuid.uuid4(),
        organizer_id=uuid.uuid4(),
        name="Test Race",
        start_at=now - timedelta(hours=5),
        end_at=now + timedelta(hours=1),
    )


def _make_face_result() -> FaceResult:
    vec = np.ones(512, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    box = FaceBox(x1=10.0, y1=10.0, x2=80.0, y2=90.0, confidence=0.95,
                  landmarks=np.zeros((5, 2), dtype=np.float32))
    return FaceResult(vector=vec, box=box)


def _make_sessions():
    return MagicMock()


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def event():
    return _make_event()


@pytest.fixture
def photo(event):
    return _make_photo(event.id)


def _setup_db_queries(mock_db, photo, event, reid_rows=None):
    """Mock db.execute to return photo, then event, then optional reid rows."""
    photo_result = MagicMock()
    photo_result.scalar_one_or_none.return_value = photo
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    reid_result = MagicMock()
    reid_result.fetchall.return_value = reid_rows or []
    mock_db.execute.side_effect = [photo_result, event_result, reid_result]


@pytest.mark.asyncio
async def test_happy_path_auto_status(mock_db, photo, event):
    _setup_db_queries(mock_db, photo, event)
    sessions = _make_sessions()
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        bbox = BibBox(0, 0, 50, 30, 0.9)
        MockDet.return_value.detect.return_value = bbox
        MockOcr.return_value.read.return_value = BibResult(number="1234", confidence=0.92)
        MockEmbed.return_value.embed.return_value = _make_face_result()

        result = await run_pipeline(str(photo.id), mock_db, sessions)

    assert result["bib_number"] == "1234"
    assert result["ai_review_status"] == AIReviewStatus.auto.value
    assert result["needs_review"] is False


@pytest.mark.asyncio
async def test_low_confidence_triggers_review_queue(mock_db, photo, event):
    _setup_db_queries(mock_db, photo, event)
    sessions = _make_sessions()
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        bbox = BibBox(0, 0, 50, 30, 0.9)
        MockDet.return_value.detect.return_value = bbox
        MockOcr.return_value.read.return_value = BibResult(number="1234", confidence=0.50)
        MockEmbed.return_value.embed.return_value = None

        result = await run_pipeline(str(photo.id), mock_db, sessions)

    assert result["ai_review_status"] == AIReviewStatus.manual_pending.value
    assert result["needs_review"] is True
    added_types = [type(c.args[0]).__name__ for c in mock_db.add.call_args_list]
    assert "ReviewQueue" in added_types


@pytest.mark.asyncio
async def test_no_bib_triggers_review_queue(mock_db, photo, event):
    _setup_db_queries(mock_db, photo, event)
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        MockDet.return_value.detect.return_value = None
        MockOcr.return_value.read.return_value = None
        MockEmbed.return_value.embed.return_value = None

        result = await run_pipeline(str(photo.id), mock_db, _make_sessions())

    assert result["bib_number"] is None
    assert result["needs_review"] is True


@pytest.mark.asyncio
async def test_reid_match_resolves_bib(mock_db, photo, event):
    reid_rows = [("5678", 0.91)]
    _setup_db_queries(mock_db, photo, event, reid_rows=reid_rows)
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        MockDet.return_value.detect.return_value = None
        MockOcr.return_value.read.return_value = None
        MockEmbed.return_value.embed.return_value = _make_face_result()

        result = await run_pipeline(str(photo.id), mock_db, _make_sessions())

    assert result["bib_number"] == "5678"
    assert result["reid_match"] == "5678"
    assert result["needs_review"] is False
