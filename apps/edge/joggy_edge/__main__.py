"""Daemon entry point — `python -m joggy_edge`.

Loads EdgeSettings, starts watcher + observer, handles SIGTERM/SIGINT
gracefully. Exits non-zero if AUTH_FAILED — systemd will retry, but ops
must fix the token first.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

from joggy_edge.config import EdgeSettings
from joggy_edge.watcher import (
    AuthRequired,
    consumer_loop,
    start_observer,
    startup_scan,
)

logger = logging.getLogger(__name__)


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


async def _run() -> int:
    settings = EdgeSettings()  # type: ignore[call-arg]
    _setup_logging(settings.log_level)
    logger.info("joggy-edge starting — inbox=%s ingest=%s", settings.inbox_dir, settings.ingest_url)

    loop = asyncio.get_running_loop()
    queue: asyncio.Queue[Path] = asyncio.Queue()

    inbox = Path(settings.inbox_dir)
    observer = start_observer(inbox, queue, loop)

    # Run startup scan first (drain anything left from previous session)
    await startup_scan(inbox, queue)

    stop_event = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler — fine for tests
            pass

    consumer_task = asyncio.create_task(consumer_loop(queue, settings))

    # Wait for either: stop signal, or consumer exits (auth failure etc.)
    stop_wait = asyncio.create_task(stop_event.wait())
    done, _pending = await asyncio.wait(
        {consumer_task, stop_wait},
        return_when=asyncio.FIRST_COMPLETED,
    )

    exit_code = 0
    try:
        if consumer_task in done:
            consumer_task.result()  # re-raise any exception
    except AuthRequired as e:
        logger.critical("Daemon stopping due to AuthRequired: %s", e)
        exit_code = 1
    except Exception:
        logger.exception("Consumer loop crashed")
        exit_code = 2

    # Shutdown sequence
    logger.info("Stopping observer + consumer …")
    observer.stop()
    observer.join(timeout=2.0)
    if not consumer_task.done():
        consumer_task.cancel()
        try:
            await consumer_task
        except (asyncio.CancelledError, Exception):
            pass

    logger.info("joggy-edge exited with code %d", exit_code)
    return exit_code


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
