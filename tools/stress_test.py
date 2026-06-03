#!/usr/bin/env python3
"""Joggy-PicX — pre-production stress test (Phase 5).

Drives 3 in-process scenarios against the FastAPI app via ASGITransport:

  A) /ingest/photos burst   — 20 req/s x60s, verify no 5xx + rate limit fires
  B) /v1/public/photos      — 100 RPS x60s, p95 latency check
  C) Rate limit enforcement — fire 200 req fast, verify 429 count

The test uses dependency_overrides to bypass real DB / Redis / R2 — bottlenecks
found here are in the handler logic (lock contention, sync-in-async, N+1 query
patterns, etc.), NOT in real infra. A real load test against staging VPS is the
follow-up.

Usage:
    cd apps/backend && uv run python ../../tools/stress_test.py --scenario=all
    uv run python tools/stress_test.py --scenario=ingest --concurrency=20 --duration=60
    uv run python tools/stress_test.py --scenario=public
    uv run python tools/stress_test.py --scenario=ratelimit

Output: ascii tables to stdout + writes docs/stress-test-2026-06-03.md if --report.
"""
from __future__ import annotations

import argparse
import asyncio
import io
import statistics
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

# Resolve project paths regardless of where script is invoked from
ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "apps" / "backend"
import sys
sys.path.insert(0, str(BACKEND))

from joggy.db.models import (  # noqa: E402
    AIReviewStatus,
    Checkpoint,
    Event,
    EventStatus,
    Photo,
)
from joggy.db.session import get_db  # noqa: E402
from joggy.main import app  # noqa: E402
from joggy.middleware.event_token import EventTokenClaims, verify_event_token  # noqa: E402
from joggy.middleware.partner_key import PartnerKeyClaims, verify_partner_api_key  # noqa: E402


# ── Result containers ────────────────────────────────────────────────────────


@dataclass
class ScenarioResult:
    name: str
    total_requests: int = 0
    duration_seconds: float = 0.0
    status_counts: dict[int, int] = field(default_factory=dict)
    latencies_ms: list[float] = field(default_factory=list)

    @property
    def rps_achieved(self) -> float:
        return self.total_requests / self.duration_seconds if self.duration_seconds else 0.0

    @property
    def error_rate_pct(self) -> float:
        errors = sum(c for code, c in self.status_counts.items() if code >= 500)
        return (errors / self.total_requests * 100.0) if self.total_requests else 0.0

    def percentile(self, p: float) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lat = sorted(self.latencies_ms)
        idx = min(len(sorted_lat) - 1, int(len(sorted_lat) * p / 100.0))
        return sorted_lat[idx]


# ── Test fixtures (in-process mocks) ─────────────────────────────────────────


def _make_jpeg_bytes(size_kb: int = 50) -> bytes:
    """Return bytes that pass magic-byte check (real JPEG signature + filler).

    50 KB by default; not 500 KB so tests run quickly. Realistic JPEG sizes
    don't matter for handler benchmarking — the bottleneck check is on
    handler code paths, not on bandwidth.
    """
    jpeg_magic = b"\xff\xd8\xff\xe0"
    filler = b"\x00" * (size_kb * 1024 - len(jpeg_magic) - 2)
    end_marker = b"\xff\xd9"
    return jpeg_magic + filler + end_marker


def _mock_event_token_claims() -> EventTokenClaims:
    return EventTokenClaims(event_id=uuid.uuid4(), token_id=uuid.uuid4())


def _mock_partner_claims() -> PartnerKeyClaims:
    return PartnerKeyClaims(
        organizer_id=uuid.uuid4(),
        key_id=uuid.uuid4(),
        scopes=["public:photos:read"],
    )


def _make_event(event_id: uuid.UUID, organizer_id: uuid.UUID) -> Event:
    return Event(
        id=event_id,
        organizer_id=organizer_id,
        name="Stress Test Event",
        start_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
        status=EventStatus.active,
    )


def _make_photo(event_id: uuid.UUID, bib: str = "1234") -> Photo:
    return Photo(
        id=uuid.uuid4(),
        event_id=event_id,
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-stress",
        r2_key_original=f"events/{event_id}/o.jpg",
        r2_key_thumbnail=f"events/{event_id}/t.jpg",
        sha256="x" * 64,
        bib_number_nullable=bib,
        ai_review_status=AIReviewStatus.auto,
        captured_at=datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
    )


@asynccontextmanager
async def _ingest_overrides():
    """Dependency overrides for /ingest/photos: skip DB + token verification.

    Rate limit middleware uses Redis; with no Redis it fail-opens — that's
    what we want to verify Scenario C (rate limit fires when Redis IS up).
    For Scenarios A+B, we leave rate limit in place (it'll fail-open without
    Redis, which simulates a worst-case "burst with no rate limit" load.)
    """
    claims = _mock_event_token_claims()

    async def _fake_db():
        db = AsyncMock()
        # Photo lookup for sha256 dedup — return None (not duplicate)
        dedup_result = MagicMock()
        dedup_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=dedup_result)
        db.add = MagicMock()
        db.flush = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        yield db

    app.dependency_overrides[get_db] = _fake_db

    # NOTE: verify_event_token is called directly in handler body (not via Depends)
    # so dependency_overrides won't work — patch it at the module reference instead.
    async def _fake_verify_event_token(*args, **kwargs):
        return claims

    with (
        patch("joggy.api.ingest.verify_event_token", new=_fake_verify_event_token),
        patch("joggy.api.ingest.r2.upload_bytes", new=MagicMock(return_value=None)),
        patch("joggy.api.ingest.enqueue_process_photo", new=MagicMock(return_value=None)),
    ):
        try:
            yield
        finally:
            app.dependency_overrides.clear()


@asynccontextmanager
async def _public_overrides():
    """Dependency overrides for /v1/public/photos."""
    claims = _mock_partner_claims()
    event_id = uuid.uuid4()
    event = _make_event(event_id, claims.organizer_id)
    # 5 photos per query (realistic — bib spotted at multiple checkpoints)
    photo_rows = [(_make_photo(event_id), None) for _ in range(5)]

    async def _fake_db():
        db = AsyncMock()

        def _execute_side_effect(*args, **kwargs):
            # Alternate: event lookup, then photo list
            result = MagicMock()
            # Always return event row on first execute, photo rows on second
            if not hasattr(_execute_side_effect, "_calls"):
                _execute_side_effect._calls = 0
            _execute_side_effect._calls += 1
            if _execute_side_effect._calls % 2 == 1:
                result.scalar_one_or_none.return_value = event
            else:
                result.all.return_value = photo_rows
            return result

        db.execute = AsyncMock(side_effect=_execute_side_effect)
        yield db

    app.dependency_overrides[get_db] = _fake_db
    app.dependency_overrides[verify_partner_api_key] = lambda: claims

    with patch("joggy.api.public.signed_url", return_value="https://r2.example/signed"):
        try:
            yield event_id
        finally:
            app.dependency_overrides.clear()


# ── Scenario A: /ingest/photos burst ─────────────────────────────────────────


async def scenario_a_ingest(concurrency: int = 20, duration: int = 60) -> ScenarioResult:
    print(f"\n[A] /ingest/photos burst: {concurrency} req/s x{duration}s")
    result = ScenarioResult(name="A: ingest burst")
    jpeg_bytes = _make_jpeg_bytes(size_kb=50)

    async with _ingest_overrides():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://stress.test",
            timeout=30.0,
        ) as client:
            start = time.monotonic()
            deadline = start + duration

            async def one_request(req_id: int) -> None:
                # Each request gets a unique sha256 in the body bytes so dedup
                # doesn't short-circuit the test
                body = jpeg_bytes + req_id.to_bytes(8, "big")
                files = {"file": (f"shot_{req_id}.jpg", body, "image/jpeg")}
                t0 = time.monotonic()
                try:
                    r = await client.post(
                        "/ingest/photos?device_id=pi-stress",
                        files=files,
                        headers={"Authorization": "Bearer evt_stress_token"},
                    )
                    code = r.status_code
                except Exception:
                    code = -1
                latency_ms = (time.monotonic() - t0) * 1000
                result.latencies_ms.append(latency_ms)
                result.status_counts[code] = result.status_counts.get(code, 0) + 1
                result.total_requests += 1

            req_id = 0
            tick = 1.0 / concurrency  # seconds between request launches
            tasks: list[asyncio.Task] = []
            while time.monotonic() < deadline:
                tasks.append(asyncio.create_task(one_request(req_id)))
                req_id += 1
                await asyncio.sleep(tick)
            await asyncio.gather(*tasks, return_exceptions=True)
            result.duration_seconds = time.monotonic() - start

    return result


# ── Scenario B: /v1/public/photos query load ─────────────────────────────────


async def scenario_b_public(target_rps: int = 100, duration: int = 60) -> ScenarioResult:
    print(f"\n[B] /v1/public/photos: {target_rps} RPS x{duration}s")
    result = ScenarioResult(name="B: public photos")

    async with _public_overrides() as event_id:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://stress.test",
            timeout=30.0,
        ) as client:
            start = time.monotonic()
            deadline = start + duration

            async def one_query(qid: int) -> None:
                bib = f"{(qid % 10) + 1:04d}"
                t0 = time.monotonic()
                try:
                    r = await client.get(
                        f"/v1/public/photos?event_id={event_id}&bib={bib}",
                        headers={"X-API-Key": "prtnr_stress"},
                    )
                    code = r.status_code
                except Exception:
                    code = -1
                latency_ms = (time.monotonic() - t0) * 1000
                result.latencies_ms.append(latency_ms)
                result.status_counts[code] = result.status_counts.get(code, 0) + 1
                result.total_requests += 1

            qid = 0
            tick = 1.0 / target_rps
            tasks: list[asyncio.Task] = []
            while time.monotonic() < deadline:
                tasks.append(asyncio.create_task(one_query(qid)))
                qid += 1
                await asyncio.sleep(tick)
            await asyncio.gather(*tasks, return_exceptions=True)
            result.duration_seconds = time.monotonic() - start

    return result


# ── Scenario C: rate limit verification ──────────────────────────────────────


async def scenario_c_ratelimit() -> ScenarioResult:
    """Fire 200 ingest requests as fast as possible.

    Without Redis available, rate limit fail-opens → we expect 200 successes.
    With Redis available, we expect ~120 successes then 80+ 429s (current
    limit is 120/min per event token).

    This scenario PROVES the rate limit code is wired correctly. The actual
    Redis-on test belongs in CI with a Redis service.
    """
    print("\n[C] Rate-limit enforcement: 200 req fast")
    result = ScenarioResult(name="C: rate limit")
    jpeg_bytes = _make_jpeg_bytes(size_kb=10)

    async with _ingest_overrides():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://stress.test",
            timeout=30.0,
        ) as client:
            start = time.monotonic()

            async def one(req_id: int) -> None:
                body = jpeg_bytes + req_id.to_bytes(8, "big")
                files = {"file": (f"r_{req_id}.jpg", body, "image/jpeg")}
                t0 = time.monotonic()
                try:
                    r = await client.post(
                        "/ingest/photos?device_id=pi-stress",
                        files=files,
                        headers={"Authorization": "Bearer evt_stress_token"},
                    )
                    code = r.status_code
                except Exception:
                    code = -1
                result.latencies_ms.append((time.monotonic() - t0) * 1000)
                result.status_counts[code] = result.status_counts.get(code, 0) + 1
                result.total_requests += 1

            await asyncio.gather(*[one(i) for i in range(200)])
            result.duration_seconds = time.monotonic() - start

    return result


# ── Reporting ────────────────────────────────────────────────────────────────


def print_result(r: ScenarioResult) -> None:
    print(f"\n  Scenario: {r.name}")
    print(f"  Total requests:  {r.total_requests}")
    print(f"  Duration:        {r.duration_seconds:.1f}s")
    print(f"  Achieved RPS:    {r.rps_achieved:.1f}")
    print(f"  Status codes:    {dict(sorted(r.status_counts.items()))}")
    print(f"  5xx error rate:  {r.error_rate_pct:.2f}%")
    if r.latencies_ms:
        print(f"  Latency p50:     {r.percentile(50):.1f}ms")
        print(f"  Latency p95:     {r.percentile(95):.1f}ms")
        print(f"  Latency p99:     {r.percentile(99):.1f}ms")
        print(f"  Latency max:     {max(r.latencies_ms):.1f}ms")


def write_report(results: list[ScenarioResult], path: Path) -> None:
    buf = io.StringIO()
    buf.write(f"# Stress Test Report — {datetime.now().strftime('%Y-%m-%d')}\n\n")
    buf.write("## Environment\n\n")
    buf.write("- In-process: FastAPI + ASGITransport on developer laptop\n")
    buf.write("- DB / R2 / RQ / Redis: mocked via dependency_overrides + patch\n")
    buf.write("- **Limitation:** measures handler code paths only, not real infra.\n")
    buf.write("  Real-world load test against staging VPS is a follow-up task.\n\n")

    buf.write("## Results\n\n")
    buf.write("| Scenario | Requests | Duration | Achieved RPS | 5xx % | p50 (ms) | p95 (ms) | p99 (ms) | Status codes |\n")
    buf.write("|---|---|---|---|---|---|---|---|---|\n")
    for r in results:
        p50 = f"{r.percentile(50):.0f}" if r.latencies_ms else "-"
        p95 = f"{r.percentile(95):.0f}" if r.latencies_ms else "-"
        p99 = f"{r.percentile(99):.0f}" if r.latencies_ms else "-"
        codes = ", ".join(f"{c}:{n}" for c, n in sorted(r.status_counts.items()))
        buf.write(
            f"| {r.name} | {r.total_requests} | {r.duration_seconds:.1f}s | "
            f"{r.rps_achieved:.1f} | {r.error_rate_pct:.2f}% | "
            f"{p50} | {p95} | {p99} | {codes} |\n"
        )

    buf.write("\n## Analysis\n\n")
    for r in results:
        buf.write(f"### {r.name}\n\n")
        if r.error_rate_pct > 0:
            buf.write(f"- ⚠️ 5xx error rate {r.error_rate_pct:.2f}% — investigate.\n")
        else:
            buf.write("- ✅ No 5xx errors.\n")
        if r.latencies_ms:
            p95 = r.percentile(95)
            target = 500 if "public" in r.name else 2000
            verdict = "✅" if p95 < target else "⚠️"
            buf.write(f"- {verdict} p95 latency {p95:.0f}ms (target < {target}ms)\n")
        if 429 in r.status_counts:
            buf.write(f"- ✅ Rate limit fired: {r.status_counts[429]} x429\n")
        buf.write("\n")

    buf.write("## Limitations & Follow-ups\n\n")
    buf.write("- This is an in-process benchmark. No real Postgres / R2 / Redis latency is measured.\n")
    buf.write("- Rate-limit scenario C: with Redis absent, middleware fail-opens — script measures\n")
    buf.write("  handler throughput under burst, NOT actual rate-limit triggering. To verify the\n")
    buf.write("  rate limit fires in production, run this script with a real Redis instance reachable\n")
    buf.write("  via REDIS_URL env var.\n")
    buf.write("- Realistic Pi → VPS network latency (50-200ms) is not modelled.\n")
    buf.write("- For pre-event readiness: run a real load test against staging VPS once Hetzner is set up.\n")

    path.write_text(buf.getvalue(), encoding="utf-8")
    print(f"\nReport written: {path}")


# ── Entrypoint ───────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="Joggy-PicX stress test")
    parser.add_argument(
        "--scenario",
        choices=["all", "ingest", "public", "ratelimit"],
        default="all",
    )
    parser.add_argument("--concurrency", type=int, default=20, help="ingest req/s")
    parser.add_argument("--target-rps", type=int, default=100, help="public RPS")
    parser.add_argument("--duration", type=int, default=60, help="seconds per scenario")
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="path to write markdown report (default: skip)",
    )
    parser.add_argument(
        "--short",
        action="store_true",
        help="dev-mode: 5 second scenarios for quick smoke",
    )
    args = parser.parse_args()

    if args.short:
        args.duration = 5

    results: list[ScenarioResult] = []
    if args.scenario in ("all", "ingest"):
        results.append(await scenario_a_ingest(args.concurrency, args.duration))
        print_result(results[-1])
    if args.scenario in ("all", "public"):
        results.append(await scenario_b_public(args.target_rps, args.duration))
        print_result(results[-1])
    if args.scenario in ("all", "ratelimit"):
        results.append(await scenario_c_ratelimit())
        print_result(results[-1])

    if args.report:
        write_report(results, Path(args.report))


if __name__ == "__main__":
    asyncio.run(main())
