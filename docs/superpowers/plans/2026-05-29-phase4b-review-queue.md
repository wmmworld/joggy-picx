# Phase 4B — Manual Review Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a full-stack Manual Review Queue — backend API endpoints + frontend UI for Internal Users to approve/reject/override-bib low-confidence photos.

**Architecture:** Backend adds `GET /internal/review-queue?event_id=` and `PATCH /internal/review-queue/{id}` to `internal.py`; each PATCH atomically updates `ReviewQueue` + `Photo` + writes `AuditLog`. Frontend replaces the skeleton `review/page.tsx` with a real TanStack Query page with bulk select, per-row approve/reject/override, and optimistic updates.

**Tech Stack:** FastAPI + SQLModel + asyncpg (backend); Next.js 15 App Router + TanStack Query + Tailwind CSS (frontend); httpx + pytest-asyncio (tests); R2 signed URLs for thumbnails.

---

## File Map

**Create:**
- `apps/backend/tests/api/__init__.py`
- `apps/backend/tests/api/test_review_queue.py`
- `apps/frontend/hooks/useReviewQueue.ts`
- `docs/cursor-tasks/phase4b-review-queue-frontend.md`

**Modify:**
- `apps/backend/joggy/api/schemas.py` — add `ReviewQueueItemOut`, `ReviewAction`
- `apps/backend/joggy/api/internal.py` — add 2 endpoints + imports
- `apps/frontend/lib/api.ts` — add `apiPatch` helper
- `apps/frontend/app/(internal)/dashboard/review/page.tsx` — replace skeleton (Cursor task)

---

## Task 1: Backend Schemas

**Files:**
- Modify: `apps/backend/joggy/api/schemas.py`

- [ ] **Step 1: Add `ReviewQueueItemOut` and `ReviewAction` to `schemas.py`**

Open `apps/backend/joggy/api/schemas.py` and add at the end of the file:

```python
import uuid
from datetime import datetime
from typing import Literal


# Phase 4B: Review Queue API schemas

class ReviewQueueItemOut(BaseModel):
    """1 item in the review queue — includes photo metadata + signed thumbnail URL."""
    queue_id: uuid.UUID
    photo_id: uuid.UUID
    reason: str                  # "low_ocr_conf" | "no_bib"
    bib_number: str | None       # AI's best guess (may be None for no_bib)
    bib_confidence: float        # 0.0–1.0
    thumbnail_url: str           # R2 pre-signed URL, expires 1h
    checkpoint_name: str | None  # checkpoint where photo was taken
    created_at: datetime


class ReviewAction(BaseModel):
    """PATCH body — approve or reject a review queue item."""
    action: Literal["approve", "reject"]
    decision_bib: str | None = None  # override bib; ignored when action == "reject"
```

Note: `uuid` and `datetime` are already imported at the top of `schemas.py`. Only add `Literal` import if not present. Check the top of the file — add `from typing import Literal` if missing.

- [ ] **Step 2: Verify import structure (no test needed — schemas are just Pydantic models)**

```bash
cd apps/backend
uv run python -c "from joggy.api.schemas import ReviewQueueItemOut, ReviewAction; print('schemas OK')"
```

Expected: `schemas OK`

- [ ] **Step 3: Commit**

```bash
git add apps/backend/joggy/api/schemas.py
git commit -m "feat(api): add ReviewQueueItemOut + ReviewAction schemas"
```

---

## Task 2: GET `/internal/review-queue` endpoint (TDD)

**Files:**
- Create: `apps/backend/tests/api/__init__.py`
- Create: `apps/backend/tests/api/test_review_queue.py`
- Modify: `apps/backend/joggy/api/internal.py`

- [ ] **Step 1: Create test package**

```bash
# Create empty __init__.py
echo "" > apps/backend/tests/api/__init__.py
```

- [ ] **Step 2: Write the failing tests**

Create `apps/backend/tests/api/test_review_queue.py`:

```python
"""Tests for GET/PATCH /internal/review-queue endpoints."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from httpx import AsyncClient, ASGITransport

from joggy.main import app
from joggy.db.session import get_db
from joggy.middleware.internal_auth import verify_internal_user, InternalUserClaims
from joggy.db.models import (
    ReviewQueue, ReviewQueueStatus, Photo, Checkpoint,
    AIReviewStatus, Event, EventStatus,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def admin_claims():
    return InternalUserClaims(
        user_id=uuid.uuid4(),
        role="admin",
        organizer_scope=[],
        event_scope=[],
    )


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def api_client(mock_db, admin_claims):
    """FastAPI test client with mocked auth + DB."""
    async def _get_db():
        yield mock_db

    app.dependency_overrides[get_db] = _get_db
    app.dependency_overrides[verify_internal_user] = lambda: admin_claims
    yield AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.clear()


def _make_event(event_id: uuid.UUID) -> Event:
    return Event(
        id=event_id,
        organizer_id=uuid.uuid4(),
        name="Test Race",
        start_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        end_at=datetime(2026, 6, 1, 12, tzinfo=timezone.utc),
        status=EventStatus.active,
    )


def _make_photo(photo_id: uuid.UUID, event_id: uuid.UUID) -> Photo:
    return Photo(
        id=photo_id,
        event_id=event_id,
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-001",
        r2_key_original=f"events/{event_id}/{photo_id}/original.jpg",
        sha256="abc123",
        bib_number_nullable="1234",
        bib_confidence=0.52,
        ai_review_status=AIReviewStatus.manual_pending,
    )


def _make_queue_item(photo_id: uuid.UUID) -> ReviewQueue:
    return ReviewQueue(
        id=uuid.uuid4(),
        photo_id=photo_id,
        reason="low_ocr_conf",
        status=ReviewQueueStatus.pending,
        created_at=datetime(2026, 6, 1, 10, tzinfo=timezone.utc),
    )


def _make_checkpoint(event_id: uuid.UUID) -> Checkpoint:
    return Checkpoint(
        id=uuid.uuid4(),
        event_id=event_id,
        name="กม.5",
        kind="km5",
        seq_order=2,
    )


# ── GET /internal/review-queue tests ────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_review_queue_returns_pending_items(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    rq = _make_queue_item(photo_id)
    checkpoint = _make_checkpoint(event_id)

    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    rows_result = MagicMock()
    rows_result.all.return_value = [(rq, photo, checkpoint)]
    mock_db.execute.side_effect = [event_result, rows_result]

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(f"/internal/review-queue?event_id={event_id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    item = data[0]
    assert item["queue_id"] == str(rq.id)
    assert item["photo_id"] == str(photo_id)
    assert item["reason"] == "low_ocr_conf"
    assert item["bib_number"] == "1234"
    assert item["bib_confidence"] == pytest.approx(0.52)
    assert item["thumbnail_url"] == "https://r2.test/signed"
    assert item["checkpoint_name"] == "กม.5"


@pytest.mark.asyncio
async def test_list_review_queue_returns_empty_when_no_items(api_client, mock_db):
    event_id = uuid.uuid4()
    event = _make_event(event_id)

    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    rows_result = MagicMock()
    rows_result.all.return_value = []
    mock_db.execute.side_effect = [event_result, rows_result]

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(f"/internal/review-queue?event_id={event_id}")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_review_queue_404_when_event_not_found(api_client, mock_db):
    event_id = uuid.uuid4()
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = event_result

    async with api_client as client:
        response = await client.get(f"/internal/review-queue?event_id={event_id}")

    assert response.status_code == 404
```

- [ ] **Step 3: Run to verify failure**

```bash
cd apps/backend
uv run pytest tests/api/test_review_queue.py -v -k "test_list"
```

Expected: `FAILED` — `ImportError` or `404` since endpoint doesn't exist yet

- [ ] **Step 4: Add imports to `internal.py`**

At the top of `apps/backend/joggy/api/internal.py`, add these imports to the existing import blocks:

```python
# Add to the sqlalchemy imports line:
from sqlalchemy import select, and_

# Add to the joggy.api.schemas imports line:
from joggy.api.schemas import (
    EventCreate,
    EventOut,
    EventStatusUpdate,
    PartnerKeyCreate,
    PartnerKeyOut,
    ReviewQueueItemOut,   # add
    ReviewAction,          # add
)

# Add to the joggy.db.models imports line:
from joggy.db.models import (
    Checkpoint, Event, EventStatus, Organizer, PartnerApiKey,
    ReviewQueue, ReviewQueueStatus,   # add
    Photo,                             # add
    AIReviewStatus,                   # add
    ActorKind, AuditLog,              # add
)

# Add after existing imports:
from joggy.services import r2
```

- [ ] **Step 5: Add GET endpoint to `internal.py`**

Add at the end of `apps/backend/joggy/api/internal.py` (before the last blank line):

```python
# ── Review Queue ─────────────────────────────────────────────────────────────

@router.get("/review-queue", response_model=list[ReviewQueueItemOut], status_code=status.HTTP_200_OK)
async def list_review_queue(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> list[ReviewQueueItemOut]:
    """List pending review-queue items for an event (max 200, sorted newest first)."""
    event = await _get_event_or_404(db, event_id)
    _ensure_staff_event_access(claims, event)

    stmt = (
        select(ReviewQueue, Photo, Checkpoint)
        .join(Photo, Photo.id == ReviewQueue.photo_id)
        .outerjoin(Checkpoint, Checkpoint.id == Photo.checkpoint_id)
        .where(
            and_(
                Photo.event_id == event_id,
                ReviewQueue.status.in_([ReviewQueueStatus.pending, ReviewQueueStatus.in_review]),
            )
        )
        .order_by(ReviewQueue.created_at.desc())
        .limit(200)
    )
    rows = (await db.execute(stmt)).all()

    result = []
    for rq, photo, checkpoint in rows:
        key = photo.r2_key_thumbnail or photo.r2_key_original
        url = r2.signed_url(key, expires_in=3600)
        result.append(
            ReviewQueueItemOut(
                queue_id=rq.id,
                photo_id=photo.id,
                reason=rq.reason,
                bib_number=photo.bib_number_nullable,
                bib_confidence=photo.bib_confidence or 0.0,
                thumbnail_url=url,
                checkpoint_name=checkpoint.name if checkpoint else None,
                created_at=rq.created_at,
            )
        )
    return result
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
uv run pytest tests/api/test_review_queue.py -v -k "test_list"
```

Expected: `3 passed`

- [ ] **Step 7: Run full suite — no regressions**

```bash
uv run pytest tests/ -v
```

Expected: 35 passed (32 previous + 3 new)

- [ ] **Step 8: Commit**

```bash
git add apps/backend/tests/api/__init__.py \
        apps/backend/tests/api/test_review_queue.py \
        apps/backend/joggy/api/schemas.py \
        apps/backend/joggy/api/internal.py
git commit -m "feat(api): GET /internal/review-queue — list pending items with signed URLs"
```

---

## Task 3: PATCH `/internal/review-queue/{queue_id}` endpoint (TDD)

**Files:**
- Modify: `apps/backend/tests/api/test_review_queue.py`
- Modify: `apps/backend/joggy/api/internal.py`

- [ ] **Step 1: Add PATCH tests to `test_review_queue.py`**

Append to the end of `apps/backend/tests/api/test_review_queue.py`:

```python
# ── PATCH /internal/review-queue/{queue_id} tests ───────────────────────────

@pytest.mark.asyncio
async def test_approve_sets_manual_approved_status(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    queue_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    rq = _make_queue_item(photo_id)
    rq.id = queue_id

    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = rq
    photo_result = MagicMock()
    photo_result.scalar_one_or_none.return_value = photo
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    mock_db.execute.side_effect = [rq_result, photo_result, event_result]

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "approve"},
        )

    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert photo.ai_review_status == AIReviewStatus.manual_approved
    assert rq.status == ReviewQueueStatus.approved
    assert rq.resolved_at is not None


@pytest.mark.asyncio
async def test_approve_with_override_bib_updates_photo(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    queue_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    rq = _make_queue_item(photo_id)
    rq.id = queue_id

    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = rq
    photo_result = MagicMock()
    photo_result.scalar_one_or_none.return_value = photo
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    mock_db.execute.side_effect = [rq_result, photo_result, event_result]

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "approve", "decision_bib": "9999"},
        )

    assert response.status_code == 200
    assert photo.bib_number_nullable == "9999"
    assert rq.decision_bib == "9999"


@pytest.mark.asyncio
async def test_reject_sets_manual_rejected_status(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    queue_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    rq = _make_queue_item(photo_id)
    rq.id = queue_id

    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = rq
    photo_result = MagicMock()
    photo_result.scalar_one_or_none.return_value = photo
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    mock_db.execute.side_effect = [rq_result, photo_result, event_result]

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "reject"},
        )

    assert response.status_code == 200
    assert photo.ai_review_status == AIReviewStatus.manual_rejected
    assert rq.status == ReviewQueueStatus.rejected


@pytest.mark.asyncio
async def test_patch_already_resolved_returns_409(api_client, mock_db):
    queue_id = uuid.uuid4()
    rq = _make_queue_item(uuid.uuid4())
    rq.id = queue_id
    rq.status = ReviewQueueStatus.approved  # already resolved

    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = rq
    mock_db.execute.return_value = rq_result

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "approve"},
        )

    assert response.status_code == 409


@pytest.mark.asyncio
async def test_patch_not_found_returns_404(api_client, mock_db):
    queue_id = uuid.uuid4()
    rq_result = MagicMock()
    rq_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = rq_result

    async with api_client as client:
        response = await client.patch(
            f"/internal/review-queue/{queue_id}",
            json={"action": "approve"},
        )

    assert response.status_code == 404
```

- [ ] **Step 2: Run to verify failures**

```bash
cd apps/backend
uv run pytest tests/api/test_review_queue.py -v -k "test_approve or test_reject or test_patch"
```

Expected: `FAILED` — `404 Not Found` since PATCH endpoint doesn't exist yet

- [ ] **Step 3: Add PATCH endpoint to `internal.py`**

Append after the `list_review_queue` function in `apps/backend/joggy/api/internal.py`:

```python
@router.patch("/review-queue/{queue_id}", status_code=status.HTTP_200_OK)
async def resolve_review_queue(
    queue_id: uuid.UUID,
    payload: ReviewAction,
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> dict:
    """Approve or reject a review queue item (with optional bib override)."""
    # 1. Load queue item
    rq_result = await db.execute(select(ReviewQueue).where(ReviewQueue.id == queue_id))
    rq = rq_result.scalar_one_or_none()
    if rq is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review queue item not found")

    # 2. Idempotency guard
    if rq.status not in (ReviewQueueStatus.pending, ReviewQueueStatus.in_review):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Item already resolved")

    # 3. Load photo + event for scope check
    photo_result = await db.execute(select(Photo).where(Photo.id == rq.photo_id))
    photo = photo_result.scalar_one_or_none()
    if photo is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

    event = await _get_event_or_404(db, photo.event_id)
    _ensure_staff_event_access(claims, event)

    # 4. Resolve
    now = datetime.now(timezone.utc)
    if payload.action == "approve":
        rq.status = ReviewQueueStatus.approved
        photo.ai_review_status = AIReviewStatus.manual_approved
        if payload.decision_bib:
            rq.decision_bib = payload.decision_bib
            photo.bib_number_nullable = payload.decision_bib
    else:
        rq.status = ReviewQueueStatus.rejected
        photo.ai_review_status = AIReviewStatus.manual_rejected

    rq.resolved_at = now
    db.add(rq)
    db.add(photo)

    # 5. AuditLog
    db.add(AuditLog(
        actor_kind=ActorKind.internal_user,
        actor_app_user_id=claims.user_id,
        action=f"review_{payload.action}d",
        target_kind="photo",
        target_id=photo.id,
        context={"queue_id": str(rq.id), "decision_bib": rq.decision_bib},
    ))

    await db.commit()
    return {"status": rq.status.value, "queue_id": str(rq.id)}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/api/test_review_queue.py -v
```

Expected: `8 passed` (3 GET + 5 PATCH)

- [ ] **Step 5: Run full suite — no regressions**

```bash
uv run pytest tests/ -v
```

Expected: 40 passed

- [ ] **Step 6: Commit**

```bash
git add apps/backend/tests/api/test_review_queue.py \
        apps/backend/joggy/api/internal.py
git commit -m "feat(api): PATCH /internal/review-queue/{id} — approve/reject + bib override"
```

---

## Task 4: Frontend — Cursor Prompt

**Files:**
- Modify: `apps/frontend/lib/api.ts`
- Create: `apps/frontend/hooks/useReviewQueue.ts`
- Modify: `apps/frontend/app/(internal)/dashboard/review/page.tsx`
- Create: `docs/cursor-tasks/phase4b-review-queue-frontend.md`

This task writes the Cursor prompt document, then commits it. **Cursor executes the actual frontend changes separately.**

- [ ] **Step 1: Create Cursor prompt file**

Create `docs/cursor-tasks/phase4b-review-queue-frontend.md` with the following content:

```markdown
# Cursor Task: Phase 4B — Manual Review Queue UI

## Context

Project: Joggy-PicX — Internal Dashboard for running event photo management.
Working directory: `apps/frontend/`
Stack: Next.js 15 App Router, TypeScript strict, TanStack Query v5, Tailwind CSS v4, `@biomejs/biome` linter.

Backend APIs are already live:
- `GET /internal/review-queue?event_id=<uuid>` — returns list of ReviewQueueItem (max 200)
- `PATCH /internal/review-queue/<queue_id>` — approve/reject/override bib

Auth pattern: all internal API calls use `apiGet`/`apiPost` helpers from `lib/api.ts` which inject Supabase JWT automatically.

## API Response Types

```typescript
// GET /internal/review-queue?event_id=...
type ReviewQueueItem = {
  queue_id: string
  photo_id: string
  reason: "low_ocr_conf" | "no_bib"
  bib_number: string | null
  bib_confidence: number  // 0.0-1.0
  thumbnail_url: string
  checkpoint_name: string | null
  created_at: string
}

// PATCH /internal/review-queue/:queue_id body
type ReviewActionPayload = {
  action: "approve" | "reject"
  decision_bib?: string | null
}

// PATCH response
type ReviewActionResponse = {
  status: "approved" | "rejected"
  queue_id: string
}
```

## Task A: Add `apiPatch` helper to `lib/api.ts`

Add a `apiPatch<T, B>` function that is identical to `apiPost` but uses method `"PATCH"`. Place it after `apiPost`. Export it.

```typescript
export async function apiPatch<T, B = unknown>(
  endpoint: string,
  body?: B
): Promise<ApiResponse<T>> {
  // identical to apiPost but method: "PATCH"
}
```

## Task B: Create `hooks/useReviewQueue.ts`

Create `apps/frontend/hooks/useReviewQueue.ts`.

```typescript
"use client"
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query"
import { apiGet, apiPatch } from "../lib/api"

export type ReviewQueueItem = {
  queue_id: string
  photo_id: string
  reason: "low_ocr_conf" | "no_bib"
  bib_number: string | null
  bib_confidence: number
  thumbnail_url: string
  checkpoint_name: string | null
  created_at: string
}

type ReviewActionPayload = {
  action: "approve" | "reject"
  decision_bib?: string | null
}

// Fetch all pending items for one event
async function getReviewQueue(eventId: string): Promise<ReviewQueueItem[]> {
  const result = await apiGet<ReviewQueueItem[]>(`/internal/review-queue?event_id=${eventId}`)
  if (!result.success) throw new Error(result.error || "Failed to fetch review queue")
  return result.data || []
}

export function useReviewQueue(eventId: string | null) {
  return useQuery({
    queryKey: ["review-queue", eventId],
    queryFn: () => getReviewQueue(eventId!),
    enabled: !!eventId,
    staleTime: 30 * 1000,
  })
}

export function useResolveItem() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: async ({
      queueId,
      payload,
    }: {
      queueId: string
      payload: ReviewActionPayload
    }) => {
      const result = await apiPatch(`/internal/review-queue/${queueId}`, payload)
      if (!result.success) throw new Error(result.error || "Failed to resolve item")
      return result.data
    },
    onMutate: async ({ queueId }) => {
      // Optimistic update — remove from list immediately
      // Cancel any in-flight refetch so it doesn't clobber the optimistic update
      return { queueId }
    },
    onSettled: (_, __, { queueId }, context) => {
      // After mutation (success or error), invalidate to sync with server
      // Note: the page handles per-item removal in onSuccess
    },
  })
}
```

## Task C: Replace `app/(internal)/dashboard/review/page.tsx`

Replace the existing skeleton with a full working page. Requirements:

### Layout

1. **Page header**: "คิวตรวจสอบรูป" (h1) + description "รูปที่ AI confidence ต่ำ รอตรวจสอบจาก staff"

2. **Event selector**: dropdown (`<select>` or styled select) that loads events using `useEvents()` hook (already exists at `hooks/useEvents.ts`). Show placeholder "— เลือกงานวิ่ง —" when no event selected. Show event name + date range in option label.

3. **Stats bar** (only when event selected): show `N รูปรอตรวจสอบ` count from queue length.

4. **Bulk action bar** (only when ≥ 1 checkbox selected):
   - "☑ N รายการที่เลือก" label
   - [✓ Approve] button — calls approve for all selected queue_ids (no decision_bib override in bulk)
   - [✗ Reject] button — calls reject for all selected queue_ids
   - Use `Promise.all()` for parallel PATCH calls

5. **Table** with columns: ☐ checkbox | รูปภาพ | บิบ (AI + override) | สาเหตุ | จุดถ่าย | การจัดการ

6. **Empty state**: "ไม่มีรูปรอตรวจสอบ ✓" when queue is empty for selected event.

7. **No event selected state**: "กรุณาเลือกงานวิ่ง" prompt.

### Table Row Details

Each row contains:

- **Checkbox**: selects item for bulk actions. "Select all" checkbox in header.

- **รูปภาพ**: `<img>` tag using `thumbnail_url` from API, size 64×64px, `object-fit: cover`, `rounded`. Click opens a lightbox modal showing the full image (just an `<img>` inside a modal overlay with backdrop click to close). On image load error show a camera icon placeholder (`📷`).

- **บิบ column**:
  - Top: AI bib number + confidence badge  
    - Badge color: green bg if confidence ≥ 0.70, yellow if 0.50–0.69, red if < 0.50
    - Show `"ไม่พบ"` if `bib_number` is null
  - Below: text input `<input type="text" placeholder="แก้ไขบิบ..." />` for override bib
    - Stores value in local React state `overrideBibs: Record<string, string>` (queue_id → value)
    - Small, muted styling

- **สาเหตุ column**: badge
  - `low_ocr_conf` → "OCR ต่ำ" (yellow badge)
  - `no_bib` → "ไม่พบบิบ" (red badge)

- **จุดถ่าย column**: `checkpoint_name` or "—" if null

- **การจัดการ column**:
  - [✓] green button — approve (sends `decision_bib` from override input if filled)
  - [✗] red button — reject
  - Both buttons show loading spinner while their specific PATCH is in progress

### Behaviour

**Per-item approve**: call `PATCH /internal/review-queue/{queue_id}` with `{ action: "approve", decision_bib: overrideBibs[queue_id] || null }`. On success: remove row from displayed list immediately (optimistic — remove from local state, do not wait for refetch). Show success toast: "อนุมัติแล้ว".

**Per-item reject**: same but `{ action: "reject" }`. Toast: "ปฏิเสธแล้ว".

**Bulk approve**: `Promise.all([...selectedIds.map(id => patch(id, {action:"approve"}))])`. Remove all from list on settle. Toast: "อนุมัติ N รายการแล้ว".

**Bulk reject**: same, toast "ปฏิเสธ N รายการแล้ว".

**On any error**: show toast "เกิดข้อผิดพลาด กรุณาลองใหม่". Do NOT remove item from list on error.

### Loading States

- While fetching queue: show 3 skeleton rows (grey animated pulse bars, same columns as real rows)
- While event list loading: show "กำลังโหลด..." in dropdown

### State Management

Use local React `useState` only — no Zustand needed:
- `selectedEventId: string | null`
- `selectedItems: Set<string>` — queue_ids checked for bulk
- `overrideBibs: Record<string, string>` — per-row override bib input
- `lightboxUrl: string | null` — if set, show lightbox modal with this image URL
- `processingIds: Set<string>` — queue_ids currently being PATCH'd (for per-row loading spinner)
- `items: ReviewQueueItem[]` — local copy of queue data (initialize from `useReviewQueue`, remove on success)

### Toast

Use a simple toast: a fixed-position div bottom-right, appears for 3s then fades. No external library needed — implement with `useState` + `useEffect` timeout.

### TypeScript

All types must be explicit — no `any`. Use the `ReviewQueueItem` type from the hook.

## Commit Instructions

After implementing Tasks A, B, and C:

```bash
git add apps/frontend/lib/api.ts \
        apps/frontend/hooks/useReviewQueue.ts \
        apps/frontend/app/(internal)/dashboard/review/page.tsx
git commit -m "feat(frontend): Review Queue UI — event filter + table + approve/reject/override"
```
```

- [ ] **Step 2: Commit the Cursor prompt**

```bash
git add docs/cursor-tasks/phase4b-review-queue-frontend.md
git commit -m "docs(cursor): Phase 4B Review Queue frontend prompt"
```

- [ ] **Step 3: Run Cursor with the prompt**

Open Cursor IDE, navigate to `apps/frontend/`, and run:
```
Use the prompt at docs/cursor-tasks/phase4b-review-queue-frontend.md to implement the Review Queue frontend UI.
```

- [ ] **Step 4: After Cursor completes — verify TypeScript**

```bash
cd apps/frontend
npx tsc -p tsconfig.json --noEmit
```

Expected: `0 errors`

- [ ] **Step 5: After Cursor completes — verify linter**

```bash
npx biome check .
```

Expected: no errors (warnings OK)

---

## Task 5: Update PROGRESS.md + CHANGELOG.md

**Files:**
- Modify: `PROGRESS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update PROGRESS.md**

In PROGRESS.md, update Done Log (add Phase 4B entries) and mark the Review Queue milestone as complete.

- [ ] **Step 2: Update CHANGELOG.md**

Add entries under `[Unreleased]`:
- `[Claude] feat(api): GET /internal/review-queue + PATCH + tests`
- `[Cursor] feat(frontend): Review Queue UI`

- [ ] **Step 3: Commit**

```bash
git add PROGRESS.md CHANGELOG.md
git commit -m "docs: update PROGRESS + CHANGELOG for Phase 4B Review Queue"
```
