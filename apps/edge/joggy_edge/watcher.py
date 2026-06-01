"""Filesystem observer + consumer loop for the edge uploader."""
from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def _today() -> datetime:
    """Wrappable for tests."""
    return datetime.now()


def _file_size(path: Path) -> int:
    """Wrappable for tests."""
    return path.stat().st_size


def is_image_file(path: Path) -> bool:
    """True if path is a JPEG/PNG and not a hidden file."""
    if path.name.startswith("."):
        return False
    return path.suffix.lower() in _IMAGE_EXTENSIONS


def scan_inbox(inbox: Path) -> list[Path]:
    """List image files in inbox (non-recursive). Sorted for deterministic order."""
    if not inbox.exists():
        return []
    return sorted(p for p in inbox.iterdir() if p.is_file() and is_image_file(p))


def wait_for_stable_size(path: Path, poll_interval: float = 0.1, max_wait: float = 2.0) -> bool:
    """Poll file size until it stops changing.

    Returns True if size is stable (2 consecutive reads equal). Returns False
    if max_wait elapsed without stabilizing — caller should skip or retry later.
    """
    deadline = time.monotonic() + max_wait
    try:
        prev = _file_size(path)
    except FileNotFoundError:
        return False
    while time.monotonic() < deadline:
        time.sleep(poll_interval)
        try:
            curr = _file_size(path)
        except FileNotFoundError:
            return False
        if curr == prev and curr > 0:
            return True
        prev = curr
    return False


def move_to_uploaded(file_path: Path, uploaded_root: Path) -> Path:
    """Move file to uploaded/YYYY-MM-DD/. Suffix `_2`, `_3`... on collision."""
    date_folder = uploaded_root / _today().strftime("%Y-%m-%d")
    date_folder.mkdir(parents=True, exist_ok=True)
    target = _resolve_collision(date_folder / file_path.name)
    file_path.rename(target)
    return target


def move_to_failed(file_path: Path, failed_root: Path) -> Path:
    """Move file to failed/ with collision suffix."""
    failed_root.mkdir(parents=True, exist_ok=True)
    target = _resolve_collision(failed_root / file_path.name)
    file_path.rename(target)
    return target


def _resolve_collision(target: Path) -> Path:
    """Return target if not exists; else append `_2`, `_3`... before extension."""
    if not target.exists():
        return target
    stem, suffix = target.stem, target.suffix
    n = 2
    while True:
        candidate = target.with_name(f"{stem}_{n}{suffix}")
        if not candidate.exists():
            return candidate
        n += 1


import asyncio

from joggy_edge.config import EdgeSettings
from joggy_edge.uploader import UploadOutcome, UploadResult, upload_with_retry  # noqa: F401 — re-exported for tests


class AuthRequired(Exception):
    """Raised when the daemon receives 401/403 — token must be fixed before continuing."""


async def consumer_loop(
    queue: "asyncio.Queue[Path]",
    settings: EdgeSettings,
    stop_after: int | None = None,
) -> None:
    """Drain queue, upload each file, dispatch to uploaded/ or failed/.

    Raises AuthRequired on AUTH_FAILED (caller stops the daemon).
    `stop_after`: if set, exits after processing N items (used in tests).
    """
    inbox = Path(settings.inbox_dir)  # noqa: F841 — accessed via settings later if needed
    uploaded_root = Path(settings.uploaded_dir)
    failed_root = Path(settings.failed_dir)
    processed = 0

    while stop_after is None or processed < stop_after:
        try:
            path = await asyncio.wait_for(queue.get(), timeout=1.0) if stop_after else await queue.get()
        except asyncio.TimeoutError:
            return

        try:
            if not path.exists():
                logger.warning("File disappeared before upload: %s", path)
                continue
            if not wait_for_stable_size(path):
                logger.warning("File size unstable, skipping (will retry on restart): %s", path)
                continue

            result: UploadResult = await upload_with_retry(path, settings)
            if result.outcome in (UploadOutcome.UPLOADED, UploadOutcome.DUPLICATE):
                target = move_to_uploaded(path, uploaded_root)
                logger.info(
                    "Uploaded %s → %s (photo_id=%s, outcome=%s)",
                    path.name, target.name, result.photo_id, result.outcome.value,
                )
            elif result.outcome == UploadOutcome.REJECTED:
                target = move_to_failed(path, failed_root)
                logger.error("Rejected %s → %s (reason=%s)", path.name, target.name, result.reason)
            elif result.outcome == UploadOutcome.AUTH_FAILED:
                logger.critical("AUTH_FAILED on %s (reason=%s) — stopping daemon", path.name, result.reason)
                raise AuthRequired(result.reason or "token rejected")
        finally:
            queue.task_done()
            processed += 1


from watchdog.events import FileCreatedEvent, FileSystemEventHandler
from watchdog.observers import Observer


async def startup_scan(inbox: Path, queue: "asyncio.Queue[Path]") -> None:
    """Enqueue all existing image files in inbox (called once at daemon start)."""
    for path in scan_inbox(inbox):
        await queue.put(path)
        logger.info("Startup scan enqueued: %s", path.name)


class _Handler(FileSystemEventHandler):
    """Translates watchdog FileCreatedEvent → queue.put_nowait via event loop."""

    def __init__(self, loop: asyncio.AbstractEventLoop, queue: "asyncio.Queue[Path]") -> None:
        super().__init__()
        self._loop = loop
        self._queue = queue

    def on_created(self, event: FileCreatedEvent) -> None:  # type: ignore[override]
        if getattr(event, "is_directory", False):
            return
        path = Path(str(event.src_path))
        if not is_image_file(path):
            return
        self._loop.call_soon_threadsafe(self._queue.put_nowait, path)


def start_observer(inbox: Path, queue: "asyncio.Queue[Path]", loop: asyncio.AbstractEventLoop) -> Observer:
    """Start watchdog Observer; caller is responsible for stop() on shutdown."""
    inbox.mkdir(parents=True, exist_ok=True)
    handler = _Handler(loop=loop, queue=queue)
    observer = Observer()
    observer.schedule(handler, str(inbox), recursive=False)
    observer.start()
    logger.info("Observer started on %s", inbox)
    return observer
