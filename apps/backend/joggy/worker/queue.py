"""
RQ queue setup — single worker queue ตาม ADR-0003.
Claude (Tech Lead) — Phase 2 Day 4 + Task 3

Usage:
    from joggy.worker.queue import enqueue_process_photo, enqueue_process_erasure
"""

from functools import lru_cache

from redis import Redis
from rq import Queue

from joggy.core.config import get_settings


@lru_cache
def get_redis() -> Redis:  # type: ignore[type-arg]
    """Cached Redis connection."""
    return Redis.from_url(get_settings().redis_url, decode_responses=False)


@lru_cache
def get_queue() -> Queue:
    """Cached RQ default queue — 1 queue ตาม ADR-0003 (single worker)."""
    return Queue("default", connection=get_redis())


def enqueue_process_photo(photo_id: str) -> str:
    """
    Enqueue AI processing job สำหรับ 1 รูป.
    Phase 3: worker จะ implement จริงด้วย ONNX pipeline (D-021)

    Returns: RQ job ID
    """
    job = get_queue().enqueue(
        "joggy.worker.tasks.process_photo",
        photo_id,
        job_timeout=300,       # 5 นาที max per photo
        result_ttl=86400,      # เก็บ result 24 ชั่วโมง
        failure_ttl=604800,    # เก็บ failed job 7 วัน
    )
    return job.id


def enqueue_process_erasure(erasure_id: str) -> str:
    """
    Enqueue Right-to-Erasure job (D-014, SLA 24h).
    Returns: RQ job ID
    """
    job = get_queue().enqueue(
        "joggy.worker.tasks.process_erasure",
        erasure_id,
        job_timeout=300,
        result_ttl=86400,
        failure_ttl=604800,
    )
    return job.id
