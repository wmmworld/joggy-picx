"""
Cloudflare R2 service — S3-compatible via boto3.
Claude (Tech Lead) — Phase 2 Day 4

Usage:
    from joggy.services.r2 import r2, r2_key_photo, signed_url
"""

from functools import lru_cache

import boto3
from botocore.config import Config

from joggy.core.config import get_settings


@lru_cache
def _get_client():  # type: ignore[return]
    """Cached boto3 S3 client ชี้ไป Cloudflare R2."""
    s = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=f"https://{s.r2_account_id}.r2.cloudflarestorage.com",
        aws_access_key_id=s.r2_access_key_id,
        aws_secret_access_key=s.r2_secret_access_key,
        region_name="auto",
        config=Config(signature_version="s3v4"),
    )


def r2_key_original(event_id: str, photo_id: str) -> str:
    return f"events/{event_id}/{photo_id}/original.jpg"


def r2_key_thumbnail(event_id: str, photo_id: str) -> str:
    return f"events/{event_id}/{photo_id}/thumbnail.jpg"


def upload_bytes(key: str, data: bytes, content_type: str = "image/jpeg") -> None:
    """อัปโหลด bytes ขึ้น R2 — sync (รันใน threadpool ถ้า async จำเป็น)."""
    _get_client().put_object(
        Bucket=get_settings().r2_bucket_name,
        Key=key,
        Body=data,
        ContentType=content_type,
    )


def download_bytes(key: str) -> bytes:
    """ดาวน์โหลด object จาก R2 เป็น bytes — ใช้โดย AI pipeline worker."""
    response = _get_client().get_object(
        Bucket=get_settings().r2_bucket_name,
        Key=key,
    )
    return response["Body"].read()


def delete_object(key: str) -> None:
    """ลบ object ใน R2 — ใช้โดย Erasure worker."""
    _get_client().delete_object(
        Bucket=get_settings().r2_bucket_name,
        Key=key,
    )


def signed_url(key: str, expires_in: int = 3600) -> str:
    """สร้าง pre-signed URL สำหรับ GET — default 1 ชั่วโมง."""
    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": get_settings().r2_bucket_name, "Key": key},
        ExpiresIn=expires_in,
    )
