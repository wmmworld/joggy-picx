"""Tests for generate_thumbnail — pure JPEG resize via Pillow."""
import io

import pytest
from PIL import Image

from joggy.services.thumbnail import ThumbnailError, generate_thumbnail


def _make_jpeg(width: int, height: int, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    """Helper: produce a valid JPEG of the requested size."""
    img = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def test_landscape_resized_to_max_400():
    src = _make_jpeg(1920, 1080)
    out = generate_thumbnail(src)
    result = Image.open(io.BytesIO(out))
    assert result.format == "JPEG"
    assert max(result.size) == 400
    # Aspect ratio ≈ 1.78 (16:9)
    assert abs(result.size[0] / result.size[1] - 1920 / 1080) < 0.01


def test_portrait_resized_to_max_400():
    src = _make_jpeg(1080, 1920)
    out = generate_thumbnail(src)
    result = Image.open(io.BytesIO(out))
    assert max(result.size) == 400
    assert result.size[1] == 400  # tallest dimension
    # Aspect ratio ≈ 0.56
    assert abs(result.size[0] / result.size[1] - 1080 / 1920) < 0.01


def test_output_is_smaller_than_input():
    src = _make_jpeg(4000, 3000)
    out = generate_thumbnail(src)
    assert len(out) < len(src)
    # Sanity check on absolute size — typical 400×300 q75 JPEG ~5-30KB
    assert len(out) < 100 * 1024  # under 100 KB


def test_already_small_not_upscaled():
    src = _make_jpeg(100, 100)
    out = generate_thumbnail(src)
    result = Image.open(io.BytesIO(out))
    # Pillow's Image.thumbnail() never upscales
    assert max(result.size) == 100


def test_invalid_bytes_raises():
    with pytest.raises(ThumbnailError):
        generate_thumbnail(b"not a jpeg at all")
