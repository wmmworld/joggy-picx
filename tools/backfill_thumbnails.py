#!/usr/bin/env python3
"""Backfill thumbnails for photos that were uploaded before thumbnail generation was added.

Processes all Photos WHERE r2_key_thumbnail IS NULL.
Skip-and-continue: errors are logged and counted; script reports summary at the end.

Usage (from apps/backend/):
    uv run python ../../tools/backfill_thumbnails.py [--dry-run] [--event-id UUID]

Options:
    --dry-run       Print what would be done without writing to R2 or DB
    --event-id UUID Limit to photos in one specific event (optional)

Examples:
    # Backfill all photos
    cd apps/backend
    uv run python ../../tools/backfill_thumbnails.py

    # Preview only (no writes)
    uv run python ../../tools/backfill_thumbnails.py --dry-run

    # Backfill one event only
    uv run python ../../tools/backfill_thumbnails.py --event-id 5ac85309-71d5-46a6-9d1c-9c3d9d769582
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from joggy.core.config import get_settings
from joggy.db.models import Photo
from joggy.services import r2
from joggy.services.thumbnail import ThumbnailError, generate_thumbnail

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def backfill(dry_run: bool = False, event_id: uuid.UUID | None = None) -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    async with AsyncSession(engine) as db:
        # Find all photos without a thumbnail
        stmt = select(Photo).where(Photo.r2_key_thumbnail.is_(None))
        if event_id is not None:
            stmt = stmt.where(Photo.event_id == event_id)
        stmt = stmt.order_by(Photo.created_at.asc())

        result = await db.execute(stmt)
        photos = list(result.scalars().all())

    await engine.dispose()  # close pool before long loop

    total = len(photos)
    logger.info("Found %d photos without thumbnails%s", total, f" (event_id={event_id})" if event_id else "")

    if total == 0:
        logger.info("Nothing to do.")
        return

    if dry_run:
        logger.info("[DRY RUN] Would process %d photos. No changes written.", total)
        for p in photos:
            logger.info("  Would process: %s (event=%s)", p.id, p.event_id)
        return

    processed = 0
    skipped = 0
    errors = 0

    engine = create_async_engine(settings.database_url)

    for i, photo in enumerate(photos, 1):
        try:
            logger.info("[%d/%d] Processing photo %s ...", i, total, photo.id)

            # Download original
            img_bytes = r2.download_bytes(photo.r2_key_original)

            # Generate thumbnail
            thumb_bytes = generate_thumbnail(img_bytes)

            # Upload thumbnail to R2
            thumb_key = r2.r2_key_thumbnail(str(photo.event_id), str(photo.id))
            r2.upload_bytes(thumb_key, thumb_bytes, content_type="image/jpeg")

            # Update DB row
            async with AsyncSession(engine) as db:
                db_photo = (await db.execute(
                    select(Photo).where(Photo.id == photo.id)
                )).scalar_one_or_none()
                if db_photo is None:
                    logger.warning("  Photo %s not found in DB (deleted?). Skipping.", photo.id)
                    skipped += 1
                    continue
                db_photo.r2_key_thumbnail = thumb_key
                await db.commit()

            processed += 1
            logger.info(
                "  ✅ Done: %s → %s (%d KB → %d KB)",
                photo.r2_key_original.split("/")[-1],
                thumb_key.split("/")[-1],
                len(img_bytes) // 1024,
                len(thumb_bytes) // 1024,
            )

        except ThumbnailError as e:
            errors += 1
            logger.error("  ❌ Thumbnail error for %s: %s (skipping)", photo.id, e)
        except Exception as e:
            errors += 1
            logger.error("  ❌ Unexpected error for %s: %s (skipping)", photo.id, e)

    await engine.dispose()

    logger.info("")
    logger.info("═" * 50)
    logger.info("Backfill complete")
    logger.info("  Processed: %d", processed)
    logger.info("  Skipped:   %d", skipped)
    logger.info("  Errors:    %d", errors)
    logger.info("  Total:     %d", total)
    logger.info("═" * 50)

    if errors > 0:
        logger.warning("%d photo(s) had errors — check logs above.", errors)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill thumbnails for existing photos")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--event-id", type=str, help="Limit to one event UUID")
    args = parser.parse_args()

    event_id: uuid.UUID | None = None
    if args.event_id:
        try:
            event_id = uuid.UUID(args.event_id)
        except ValueError:
            print(f"ERROR: Invalid event-id UUID: {args.event_id}", file=sys.stderr)
            sys.exit(1)

    asyncio.run(backfill(dry_run=args.dry_run, event_id=event_id))


if __name__ == "__main__":
    main()
