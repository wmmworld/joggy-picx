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
