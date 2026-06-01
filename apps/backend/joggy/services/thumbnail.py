"""Thumbnail generation — pure in-memory JPEG resize via Pillow.

Used by the RQ worker (pipeline.py) to produce ~50KB previews of the
~6MB originals so the Photo Gallery loads quickly.

Best-effort: caller is expected to log + skip on ThumbnailError.
"""
from __future__ import annotations

from io import BytesIO

from PIL import Image, UnidentifiedImageError


class ThumbnailError(Exception):
    """Raised when the input cannot be decoded or resized."""


def generate_thumbnail(
    jpeg_bytes: bytes,
    max_dim: int = 400,
    quality: int = 75,
) -> bytes:
    """Resize JPEG to fit within `max_dim`x`max_dim`, preserve aspect ratio.

    Returns JPEG bytes (~30-60 KB for typical 6 MB camera input).
    Raises ThumbnailError on decode/resize failure.
    """
    try:
        img = Image.open(BytesIO(jpeg_bytes))
        img.thumbnail((max_dim, max_dim))  # in-place, preserves aspect ratio
        out = BytesIO()
        img.convert("RGB").save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
    except (UnidentifiedImageError, OSError) as exc:
        raise ThumbnailError(f"Cannot decode/resize JPEG: {exc}") from exc
