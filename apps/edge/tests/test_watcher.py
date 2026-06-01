"""Tests for watcher — file move helpers + extension filter + scan."""
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_dirs(tmp_path: Path) -> tuple[Path, Path, Path]:
    inbox = tmp_path / "inbox"
    uploaded = tmp_path / "uploaded"
    failed = tmp_path / "failed"
    for d in (inbox, uploaded, failed):
        d.mkdir()
    return inbox, uploaded, failed


def test_move_to_uploaded_creates_date_folder(tmp_path):
    from joggy_edge.watcher import move_to_uploaded

    inbox, uploaded, _ = _make_dirs(tmp_path)
    f = inbox / "photo.jpg"
    f.write_bytes(b"x")

    fixed_date = datetime(2026, 6, 1)
    with patch("joggy_edge.watcher._today", return_value=fixed_date):
        result = move_to_uploaded(f, uploaded)

    assert not f.exists()
    expected = uploaded / "2026-06-01" / "photo.jpg"
    assert expected.exists()
    assert result == expected


def test_move_to_uploaded_suffix_on_collision(tmp_path):
    from joggy_edge.watcher import move_to_uploaded

    inbox, uploaded, _ = _make_dirs(tmp_path)
    fixed_date = datetime(2026, 6, 1)
    date_folder = uploaded / "2026-06-01"
    date_folder.mkdir()
    existing = date_folder / "photo.jpg"
    existing.write_bytes(b"old")

    new_file = inbox / "photo.jpg"
    new_file.write_bytes(b"new")

    with patch("joggy_edge.watcher._today", return_value=fixed_date):
        result = move_to_uploaded(new_file, uploaded)

    assert existing.read_bytes() == b"old"
    assert result == date_folder / "photo_2.jpg"
    assert result.read_bytes() == b"new"


def test_move_to_failed(tmp_path):
    from joggy_edge.watcher import move_to_failed

    inbox, _, failed = _make_dirs(tmp_path)
    f = inbox / "bad.jpg"
    f.write_bytes(b"x")

    result = move_to_failed(f, failed)

    assert not f.exists()
    assert result == failed / "bad.jpg"
    assert result.exists()


def test_is_image_file_accepts_jpeg_and_png():
    from joggy_edge.watcher import is_image_file

    assert is_image_file(Path("a.jpg"))
    assert is_image_file(Path("a.jpeg"))
    assert is_image_file(Path("a.JPG"))
    assert is_image_file(Path("a.png"))
    assert is_image_file(Path("a.PNG"))


def test_is_image_file_rejects_other():
    from joggy_edge.watcher import is_image_file

    assert not is_image_file(Path("a.txt"))
    assert not is_image_file(Path("a.tmp"))
    assert not is_image_file(Path("a"))
    assert not is_image_file(Path(".hidden.jpg"))


def test_scan_inbox_returns_image_files_only(tmp_path):
    from joggy_edge.watcher import scan_inbox

    inbox, _, _ = _make_dirs(tmp_path)
    (inbox / "a.jpg").write_bytes(b"")
    (inbox / "b.png").write_bytes(b"")
    (inbox / "c.txt").write_bytes(b"")
    (inbox / "d.tmp").write_bytes(b"")
    (inbox / ".hidden.jpg").write_bytes(b"")

    results = sorted(p.name for p in scan_inbox(inbox))
    assert results == ["a.jpg", "b.png"]


def test_wait_for_stable_size_returns_true_when_stable(tmp_path):
    from joggy_edge.watcher import wait_for_stable_size

    f = tmp_path / "x.jpg"
    f.write_bytes(b"hello")
    assert wait_for_stable_size(f, poll_interval=0.01, max_wait=0.1) is True


def test_wait_for_stable_size_returns_false_when_growing(tmp_path, monkeypatch):
    """File whose size keeps changing returns False after max_wait."""
    from joggy_edge.watcher import wait_for_stable_size

    f = tmp_path / "x.jpg"
    f.write_bytes(b"a")
    sizes = iter([1, 2, 3, 4, 5, 6])
    monkeypatch.setattr(
        "joggy_edge.watcher._file_size",
        lambda p: next(sizes, 99),
    )
    assert wait_for_stable_size(f, poll_interval=0.01, max_wait=0.05) is False


import asyncio
from unittest.mock import AsyncMock

from joggy_edge.config import EdgeSettings
from joggy_edge.uploader import UploadOutcome, UploadResult


@pytest.fixture
def settings_for_watch(tmp_path, monkeypatch):
    monkeypatch.setenv("INGEST_URL", "https://vps.example/ingest/photos")
    monkeypatch.setenv("EVENT_TOKEN", "evt")
    monkeypatch.setenv("INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("UPLOADED_DIR", str(tmp_path / "uploaded"))
    monkeypatch.setenv("FAILED_DIR", str(tmp_path / "failed"))
    s = EdgeSettings(_env_file=None)  # type: ignore[call-arg]
    for d in (s.inbox_dir, s.uploaded_dir, s.failed_dir):
        Path(d).mkdir(parents=True, exist_ok=True)
    return s


@pytest.mark.asyncio
async def test_consumer_uploaded_moves_to_uploaded_folder(settings_for_watch, monkeypatch):
    from joggy_edge import watcher

    f = Path(settings_for_watch.inbox_dir) / "good.jpg"
    f.write_bytes(b"x")

    monkeypatch.setattr(
        watcher,
        "upload_with_retry",
        AsyncMock(return_value=UploadResult(outcome=UploadOutcome.UPLOADED, photo_id="p", job_id="j")),
    )
    monkeypatch.setattr(
        watcher, "wait_for_stable_size", lambda p, **kw: True
    )

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await queue.put(f)

    task = asyncio.create_task(watcher.consumer_loop(queue, settings_for_watch, stop_after=1))
    await task

    assert not f.exists()
    assert any(Path(settings_for_watch.uploaded_dir).rglob("good.jpg"))


@pytest.mark.asyncio
async def test_consumer_rejected_moves_to_failed_folder(settings_for_watch, monkeypatch):
    from joggy_edge import watcher

    f = Path(settings_for_watch.inbox_dir) / "bad.jpg"
    f.write_bytes(b"x")

    monkeypatch.setattr(
        watcher,
        "upload_with_retry",
        AsyncMock(return_value=UploadResult(outcome=UploadOutcome.REJECTED, reason="too large")),
    )
    monkeypatch.setattr(watcher, "wait_for_stable_size", lambda p, **kw: True)

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await queue.put(f)
    await watcher.consumer_loop(queue, settings_for_watch, stop_after=1)

    assert not f.exists()
    assert (Path(settings_for_watch.failed_dir) / "bad.jpg").exists()


@pytest.mark.asyncio
async def test_consumer_auth_failed_raises_authrequired(settings_for_watch, monkeypatch):
    from joggy_edge import watcher
    from joggy_edge.watcher import AuthRequired

    f = Path(settings_for_watch.inbox_dir) / "x.jpg"
    f.write_bytes(b"x")

    monkeypatch.setattr(
        watcher,
        "upload_with_retry",
        AsyncMock(return_value=UploadResult(outcome=UploadOutcome.AUTH_FAILED, reason="invalid")),
    )
    monkeypatch.setattr(watcher, "wait_for_stable_size", lambda p, **kw: True)

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await queue.put(f)

    with pytest.raises(AuthRequired):
        await watcher.consumer_loop(queue, settings_for_watch, stop_after=1)


@pytest.mark.asyncio
async def test_consumer_skips_when_size_unstable(settings_for_watch, monkeypatch):
    from joggy_edge import watcher

    f = Path(settings_for_watch.inbox_dir) / "growing.jpg"
    f.write_bytes(b"x")

    upload_mock = AsyncMock()
    monkeypatch.setattr(watcher, "upload_with_retry", upload_mock)
    monkeypatch.setattr(watcher, "wait_for_stable_size", lambda p, **kw: False)

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await queue.put(f)
    await watcher.consumer_loop(queue, settings_for_watch, stop_after=1)

    upload_mock.assert_not_called()
    assert f.exists()  # left in inbox


@pytest.mark.asyncio
async def test_startup_scan_enqueues_existing_files(settings_for_watch):
    from joggy_edge.watcher import startup_scan

    inbox = Path(settings_for_watch.inbox_dir)
    (inbox / "a.jpg").write_bytes(b"")
    (inbox / "b.png").write_bytes(b"")
    (inbox / "c.txt").write_bytes(b"")  # should be skipped

    queue: asyncio.Queue[Path] = asyncio.Queue()
    await startup_scan(inbox, queue)

    enqueued = []
    while not queue.empty():
        enqueued.append(queue.get_nowait().name)
    assert sorted(enqueued) == ["a.jpg", "b.png"]


def test_make_handler_enqueues_image_create(settings_for_watch, tmp_path):
    """FileCreatedEvent for image triggers queue.put_nowait."""
    from joggy_edge.watcher import _Handler

    loop_calls: list[Path] = []
    class FakeLoop:
        def call_soon_threadsafe(self, fn, *args):
            fn(*args)
    queue_calls: list[Path] = []
    class FakeQueue:
        def put_nowait(self, item):
            queue_calls.append(item)

    handler = _Handler(loop=FakeLoop(), queue=FakeQueue())  # type: ignore[arg-type]

    class FakeEvent:
        def __init__(self, src_path: str, is_directory: bool = False):
            self.src_path = src_path
            self.is_directory = is_directory

    handler.on_created(FakeEvent(str(tmp_path / "img.jpg")))
    handler.on_created(FakeEvent(str(tmp_path / "notes.txt")))  # not image
    handler.on_created(FakeEvent(str(tmp_path), is_directory=True))  # directory

    assert queue_calls == [Path(tmp_path / "img.jpg")]
