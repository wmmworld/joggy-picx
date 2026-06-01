#!/usr/bin/env python3
"""Generate a Per-Event Upload Token (D-017) — one-shot CLI for manual testing.

Usage:
    cd apps/backend
    uv run python ../../tools/generate_event_token.py <event_uuid>

Prints the plaintext token ONCE — paste it into the Pi's .env EVENT_TOKEN.
"""
from __future__ import annotations

import asyncio
import secrets
import sys
import uuid

import argon2
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from joggy.core.config import get_settings
from joggy.db.models import AppUser, Event, EventToken, UserRole


async def main(event_id_str: str) -> int:
    try:
        event_id = uuid.UUID(event_id_str)
    except ValueError:
        print(f"ERROR: '{event_id_str}' is not a valid UUID", file=sys.stderr)
        return 1

    settings = get_settings()
    engine = create_async_engine(settings.database_url)

    # Generate plaintext token
    plaintext = f"evt_{secrets.token_urlsafe(32)}"
    token_prefix = plaintext[:8]

    # Argon2 hash
    ph = argon2.PasswordHasher()
    token_hash = ph.hash(plaintext)

    async with AsyncSession(engine) as db:
        # Load event
        event = (await db.execute(select(Event).where(Event.id == event_id))).scalar_one_or_none()
        if event is None:
            print(f"ERROR: Event {event_id} not found", file=sys.stderr)
            return 2

        # Find any admin user (issued_by)
        admin = (await db.execute(
            select(AppUser).where(AppUser.role == UserRole.admin).limit(1)
        )).scalar_one_or_none()
        if admin is None:
            print("ERROR: No admin user found in app_users", file=sys.stderr)
            return 3

        # DB column is TIMESTAMP WITHOUT TIME ZONE — strip tzinfo if present
        from datetime import timezone as _tz
        end_at_naive = event.end_at.astimezone(_tz.utc).replace(tzinfo=None) \
            if event.end_at and event.end_at.tzinfo else event.end_at

        token = EventToken(
            event_id=event.id,
            token_hash=token_hash,
            token_prefix=token_prefix,
            expires_at=end_at_naive,
            issued_by_app_user_id=admin.id,
        )
        db.add(token)
        # Capture values before session closes (avoids DetachedInstanceError)
        event_name = event.name
        event_id_out = event.id
        event_end_at = event.end_at
        await db.commit()

    print("")
    print("=" * 60)
    print("EVENT TOKEN GENERATED (save it — plaintext shown ONCE)")
    print("=" * 60)
    print(f"Event:        {event_name}")
    print(f"Event ID:     {event_id_out}")
    print(f"Token prefix: {token_prefix}")
    print(f"Expires at:   {event_end_at}")
    print()
    print(f"EVENT_TOKEN={plaintext}")
    print("=" * 60)
    print("")
    print("Paste the EVENT_TOKEN= line into Pi's /home/pi/joggy/.env")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: generate_event_token.py <event_uuid>", file=sys.stderr)
        sys.exit(1)
    sys.exit(asyncio.run(main(sys.argv[1])))
