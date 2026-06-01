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
