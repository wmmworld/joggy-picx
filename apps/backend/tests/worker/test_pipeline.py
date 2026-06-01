import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from joggy.ai.bib_detector import BibBox
from joggy.ai.bib_ocr import BibResult
from joggy.ai.face_embedder import FaceResult, FaceBox
from joggy.db.models import AIReviewStatus, Photo, Event, ReviewQueue, ReviewQueueStatus
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


def _make_execute_result(value, *, is_fetchall=False):
    """Wrap a value in a MagicMock that mimics an execute result."""
    m = MagicMock()
    if is_fetchall:
        m.fetchall.return_value = value
    else:
        m.scalar_one_or_none.return_value = value
    return m


def _setup_db_queries(mock_db, photo, event, reid_rows=None, existing_rq=None):
    """
    Stage db.execute side_effects.

    The order in the pipeline depends on the execution path:
      - Always: photo, event
      - If face + no bib: reid query
      - If needs_review: ReviewQueue existence check

    Pass exactly the results matching the test's execution path.
    """
    photo_result = _make_execute_result(photo)
    event_result = _make_execute_result(event)
    reid_result = _make_execute_result(reid_rows or [], is_fetchall=True)
    rq_result = _make_execute_result(existing_rq)
    mock_db.execute.side_effect = [photo_result, event_result, reid_result, rq_result]


@pytest.mark.asyncio
async def test_happy_path_auto_status(mock_db, photo, event):
    # Execution path: photo, event  (bib ok -> no reid, no review_queue)
    photo_result = _make_execute_result(photo)
    event_result = _make_execute_result(event)
    mock_db.execute.side_effect = [photo_result, event_result]

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
    # Execution path: photo, event, ReviewQueue check (no reid: no face_result)
    photo_result = _make_execute_result(photo)
    event_result = _make_execute_result(event)
    rq_result = _make_execute_result(None)  # no existing ReviewQueue
    mock_db.execute.side_effect = [photo_result, event_result, rq_result]

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
    # Execution path: photo, event, ReviewQueue check (no reid: no face_result)
    photo_result = _make_execute_result(photo)
    event_result = _make_execute_result(event)
    rq_result = _make_execute_result(None)  # no existing ReviewQueue
    mock_db.execute.side_effect = [photo_result, event_result, rq_result]

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
    # Execution path: photo, event, reid (face + no bib -> reid succeeds -> no review_queue)
    reid_rows = [("5678", 0.91)]
    photo_result = _make_execute_result(photo)
    event_result = _make_execute_result(event)
    reid_result = _make_execute_result(reid_rows, is_fetchall=True)
    mock_db.execute.side_effect = [photo_result, event_result, reid_result]

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


@pytest.mark.asyncio
async def test_already_reviewed_photo_skips_pipeline(mock_db, photo, event):
    photo.ai_review_status = AIReviewStatus.manual_approved
    photo.bib_number_nullable = "9999"
    # Only load photo — early return before event load
    photo_result = _make_execute_result(photo)
    mock_db.execute.side_effect = [photo_result]

    sessions = _make_sessions()
    result = await run_pipeline(str(photo.id), mock_db, sessions)

    assert result["skipped_reason"] == "already_reviewed"
    assert result["bib_number"] == "9999"
    assert mock_db.add.call_count == 0   # nothing added


@pytest.mark.asyncio
async def test_existing_review_queue_not_duplicated(mock_db, photo, event):
    """If a ReviewQueue row already exists for the photo, don't insert a duplicate."""
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    # Execution path: photo, event, ReviewQueue check returns existing row
    photo_result = _make_execute_result(photo)
    event_result = _make_execute_result(event)
    existing_rq = ReviewQueue(photo_id=photo.id, reason="no_bib", status=ReviewQueueStatus.pending)
    rq_result = _make_execute_result(existing_rq)
    mock_db.execute.side_effect = [photo_result, event_result, rq_result]

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        MockDet.return_value.detect.return_value = None
        MockOcr.return_value.read.return_value = None
        MockEmbed.return_value.embed.return_value = None

        await run_pipeline(str(photo.id), mock_db, _make_sessions())

    # Should NOT have added a new ReviewQueue
    added_types = [type(c.args[0]).__name__ for c in mock_db.add.call_args_list]
    assert added_types.count("ReviewQueue") == 0


@pytest.mark.asyncio
async def test_thumbnail_uploaded_and_key_written(mock_db, photo, event):
    _setup_db_queries(mock_db, photo, event)
    sessions = _make_sessions()
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.generate_thumbnail", return_value=b"thumb-bytes") as mock_thumb, \
         patch("joggy.worker.pipeline.r2.upload_bytes") as mock_upload, \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        MockDet.return_value.detect.return_value = None
        MockOcr.return_value.read.return_value = None
        MockEmbed.return_value.embed.return_value = None

        await run_pipeline(str(photo.id), mock_db, sessions)

    mock_thumb.assert_called_once_with(b"jpg")
    mock_upload.assert_called_once()
    upload_args = mock_upload.call_args
    # First positional arg is the R2 key
    thumb_key = upload_args.args[0]
    assert thumb_key.startswith(f"events/{photo.event_id}/")
    assert thumb_key.endswith("/thumbnail.jpg")
    assert photo.r2_key_thumbnail == thumb_key


@pytest.mark.asyncio
async def test_thumbnail_failure_does_not_break_pipeline(mock_db, photo, event):
    """ThumbnailError is caught, logged, pipeline continues. r2_key_thumbnail stays None."""
    from joggy.services.thumbnail import ThumbnailError

    _setup_db_queries(mock_db, photo, event)
    sessions = _make_sessions()
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)
    photo.r2_key_thumbnail = None  # baseline

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.generate_thumbnail", side_effect=ThumbnailError("bad jpeg")), \
         patch("joggy.worker.pipeline.r2.upload_bytes") as mock_upload, \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        MockDet.return_value.detect.return_value = None
        MockOcr.return_value.read.return_value = None
        MockEmbed.return_value.embed.return_value = None

        result = await run_pipeline(str(photo.id), mock_db, sessions)

    mock_upload.assert_not_called()
    assert photo.r2_key_thumbnail is None
    # Pipeline still completed and returned a summary
    assert result["photo_id"] == str(photo.id)
