# Phase 4C — Photo Gallery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a paginated photo gallery page to the Internal Dashboard — staff can browse all photos for an event in a 3–4 column grid, filter by bib/checkpoint/AI status, and paginate through 1,000 photos.

**Architecture:** Backend adds `GET /internal/events/{event_id}/photos` with filter + pagination query params. Frontend creates `useEventPhotos` TanStack Query hook + a `photos/page.tsx` gallery page + adds a "ดูรูปภาพ" link button to the event detail page.

**Tech Stack:** FastAPI + SQLModel (backend, TDD with httpx); Next.js 15 App Router + TanStack Query + Tailwind CSS (frontend, Cursor task).

---

## File Map

**Create:**
- `apps/backend/tests/api/test_event_photos.py`
- `apps/frontend/hooks/useEventPhotos.ts`
- `apps/frontend/app/(internal)/dashboard/events/[id]/photos/page.tsx`
- `docs/cursor-tasks/phase4c-photo-gallery-frontend.md`

**Modify:**
- `apps/backend/joggy/api/schemas.py` — add `PhotoItemOut`, `EventPhotosOut`
- `apps/backend/joggy/api/internal.py` — add endpoint + imports
- `apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx` — add "ดูรูปภาพ" link

---

## Task 1: Backend Schemas

**Files:**
- Modify: `apps/backend/joggy/api/schemas.py`

- [ ] **Step 1: Append `PhotoItemOut` and `EventPhotosOut` to `schemas.py`**

Open `apps/backend/joggy/api/schemas.py`. The file already imports `uuid`, `datetime`, `BaseModel`, `Field`, `Literal`, `field_validator`. No new imports needed for this task.

Add at the end of the file:

```python
# Phase 4C: Photo Gallery API schemas

class PhotoItemOut(BaseModel):
    """Single photo item in the gallery response."""
    photo_id: uuid.UUID
    bib_number: str | None        # Photo.bib_number_nullable
    bib_confidence: float | None  # 0.0–1.0 or None when no bib detected
    ai_review_status: str         # enum value: auto|manual_pending|manual_approved|manual_rejected
    thumbnail_url: str | None     # R2 signed URL (expires 1h); None if no key available
    checkpoint_name: str | None
    captured_at: datetime | None


class EventPhotosOut(BaseModel):
    """Paginated photo gallery response."""
    items: list[PhotoItemOut]
    total: int     # total matching records (for pagination UI)
    page: int
    per_page: int
    pages: int     # ceil(total / per_page)
```

- [ ] **Step 2: Verify imports work**

```bash
cd apps/backend
uv run python -c "from joggy.api.schemas import PhotoItemOut, EventPhotosOut; print('schemas OK')"
```

Expected: `schemas OK`

- [ ] **Step 3: Commit**

```bash
git add apps/backend/joggy/api/schemas.py
git commit -m "feat(api): add PhotoItemOut + EventPhotosOut schemas for photo gallery

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 2: `GET /internal/events/{event_id}/photos` endpoint (TDD)

**Files:**
- Create: `apps/backend/tests/api/test_event_photos.py`
- Modify: `apps/backend/joggy/api/internal.py`

- [ ] **Step 1: Write the failing tests**

Create `apps/backend/tests/api/test_event_photos.py`:

```python
"""Tests for GET /internal/events/{event_id}/photos endpoint."""
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from joggy.main import app
from joggy.db.session import get_db
from joggy.middleware.internal_auth import verify_internal_user, InternalUserClaims
from joggy.db.models import (
    Photo, Checkpoint, AIReviewStatus, Event, EventStatus,
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
    from unittest.mock import AsyncMock
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def api_client(mock_db, admin_claims):
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


def _make_photo(
    photo_id: uuid.UUID,
    event_id: uuid.UUID,
    bib: str | None = "1234",
    status: AIReviewStatus = AIReviewStatus.auto,
) -> Photo:
    return Photo(
        id=photo_id,
        event_id=event_id,
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-001",
        r2_key_original=f"events/{event_id}/{photo_id}/original.jpg",
        sha256="abc123",
        bib_number_nullable=bib,
        bib_confidence=0.85 if bib else None,
        ai_review_status=status,
        captured_at=datetime(2026, 6, 1, 9, tzinfo=timezone.utc),
    )


def _make_checkpoint(event_id: uuid.UUID, name: str = "กม.5") -> Checkpoint:
    return Checkpoint(
        id=uuid.uuid4(),
        event_id=event_id,
        name=name,
        kind="km5",
        seq_order=2,
    )


def _setup_db(mock_db, event, total: int, rows: list):
    """Stage mock_db.execute: event lookup → count → paginated rows."""
    from unittest.mock import AsyncMock
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event

    count_result = MagicMock()
    count_result.scalar_one.return_value = total

    rows_result = MagicMock()
    rows_result.all.return_value = rows

    mock_db.execute.side_effect = [event_result, count_result, rows_result]


# ── Tests ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_event_photos_returns_paginated_items(api_client, mock_db):
    event_id = uuid.uuid4()
    photo_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(photo_id, event_id)
    checkpoint = _make_checkpoint(event_id)
    _setup_db(mock_db, event, total=1, rows=[(photo, checkpoint)])

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(f"/internal/events/{event_id}/photos")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["page"] == 1
    assert data["per_page"] == 24
    assert data["pages"] == 1
    assert len(data["items"]) == 1
    item = data["items"][0]
    assert item["photo_id"] == str(photo_id)
    assert item["bib_number"] == "1234"
    assert item["ai_review_status"] == "auto"
    assert item["thumbnail_url"] == "https://r2.test/signed"
    assert item["checkpoint_name"] == "กม.5"


@pytest.mark.asyncio
async def test_list_event_photos_pagination_metadata(api_client, mock_db):
    event_id = uuid.uuid4()
    event = _make_event(event_id)
    # 50 total, page 2, 24 per page → pages = 3
    photo_id = uuid.uuid4()
    photo = _make_photo(photo_id, event_id)
    _setup_db(mock_db, event, total=50, rows=[(photo, None)])

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(
                f"/internal/events/{event_id}/photos?page=2&per_page=24"
            )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 50
    assert data["page"] == 2
    assert data["pages"] == 3


@pytest.mark.asyncio
async def test_list_event_photos_no_checkpoint_returns_none(api_client, mock_db):
    event_id = uuid.uuid4()
    event = _make_event(event_id)
    photo = _make_photo(uuid.uuid4(), event_id)
    _setup_db(mock_db, event, total=1, rows=[(photo, None)])  # No checkpoint

    with patch("joggy.api.internal.r2.signed_url", return_value="https://r2.test/signed"):
        async with api_client as client:
            response = await client.get(f"/internal/events/{event_id}/photos")

    assert response.status_code == 200
    assert response.json()["items"][0]["checkpoint_name"] is None


@pytest.mark.asyncio
async def test_list_event_photos_invalid_ai_status_returns_422(api_client, mock_db):
    event_id = uuid.uuid4()
    event = _make_event(event_id)
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    mock_db.execute.return_value = event_result

    async with api_client as client:
        response = await client.get(
            f"/internal/events/{event_id}/photos?ai_status=invalid_value"
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_list_event_photos_event_not_found_returns_404(api_client, mock_db):
    event_id = uuid.uuid4()
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = event_result

    async with api_client as client:
        response = await client.get(f"/internal/events/{event_id}/photos")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_event_photos_per_page_over_limit_returns_422(api_client, mock_db):
    event_id = uuid.uuid4()
    async with api_client as client:
        response = await client.get(
            f"/internal/events/{event_id}/photos?per_page=101"
        )
    assert response.status_code == 422
```

- [ ] **Step 2: Run to verify failures**

```bash
cd apps/backend
uv run pytest tests/api/test_event_photos.py -v
```

Expected: `FAILED` — `404 Not Found` (endpoint doesn't exist yet)

- [ ] **Step 3: Add imports + endpoint to `internal.py`**

**Add to existing imports in `apps/backend/joggy/api/internal.py`:**

```python
# Add to the existing fastapi import line:
from fastapi import APIRouter, Depends, HTTPException, Query, status

# Add to the existing sqlalchemy import line:
from sqlalchemy import select, and_, func

# Add to the existing schemas import block:
from joggy.api.schemas import (
    EventCreate,
    EventOut,
    EventStatusUpdate,
    PartnerKeyCreate,
    PartnerKeyOut,
    ReviewQueueItemOut,
    ReviewAction,
    PhotoItemOut,     # add
    EventPhotosOut,   # add
)

# Add at the top of the file (after existing imports):
from math import ceil
```

**Add the endpoint at the end of `apps/backend/joggy/api/internal.py`** (after the `resolve_review_queue` function):

```python
# ── Photo Gallery ─────────────────────────────────────────────────────────────

@router.get(
    "/events/{event_id}/photos",
    response_model=EventPhotosOut,
    status_code=status.HTTP_200_OK,
)
async def list_event_photos(
    event_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=24, ge=1, le=100),
    bib: str | None = Query(default=None),
    checkpoint_id: uuid.UUID | None = Query(default=None),
    ai_status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    claims: InternalUserClaims = Depends(verify_internal_user),
) -> EventPhotosOut:
    """Paginated photo gallery for an event — filter by bib/checkpoint/ai_status."""
    event = await _get_event_or_404(db, event_id)
    _ensure_staff_event_access(claims, event)

    # Validate ai_status query param
    ai_status_enum: AIReviewStatus | None = None
    if ai_status is not None:
        try:
            ai_status_enum = AIReviewStatus(ai_status)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid ai_status '{ai_status}'. Valid values: auto, manual_pending, manual_approved, manual_rejected",
            )

    # Build WHERE conditions
    conditions: list = [Photo.event_id == event_id]
    if bib:
        conditions.append(Photo.bib_number_nullable.ilike(f"%{bib}%"))
    if checkpoint_id:
        conditions.append(Photo.checkpoint_id == checkpoint_id)
    if ai_status_enum is not None:
        conditions.append(Photo.ai_review_status == ai_status_enum)

    # Count total matching records
    count_stmt = select(func.count(Photo.id)).where(and_(*conditions))
    total: int = (await db.execute(count_stmt)).scalar_one()

    # Fetch paginated results with checkpoint join
    stmt = (
        select(Photo, Checkpoint)
        .outerjoin(Checkpoint, Checkpoint.id == Photo.checkpoint_id)
        .where(and_(*conditions))
        .order_by(Photo.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = (await db.execute(stmt)).all()

    # Build response items
    items = []
    for photo, checkpoint in rows:
        key = photo.r2_key_thumbnail or photo.r2_key_original
        url = r2.signed_url(key, expires_in=3600)
        items.append(
            PhotoItemOut(
                photo_id=photo.id,
                bib_number=photo.bib_number_nullable,
                bib_confidence=photo.bib_confidence,
                ai_review_status=(
                    photo.ai_review_status.value
                    if hasattr(photo.ai_review_status, "value")
                    else str(photo.ai_review_status)
                ),
                thumbnail_url=url,
                checkpoint_name=checkpoint.name if checkpoint else None,
                captured_at=photo.captured_at,
            )
        )

    pages = max(1, ceil(total / per_page))
    return EventPhotosOut(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/api/test_event_photos.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Run full suite — no regressions**

```bash
uv run pytest tests/ -v
```

Expected: 46 passed (40 previous + 6 new)

- [ ] **Step 6: Commit**

```bash
git add apps/backend/tests/api/test_event_photos.py \
        apps/backend/joggy/api/internal.py
git commit -m "feat(api): GET /internal/events/{id}/photos — paginated gallery with filters

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Cursor Frontend Prompt

**Files:**
- Create: `docs/cursor-tasks/phase4c-photo-gallery-frontend.md`

- [ ] **Step 1: Create the Cursor prompt file**

Create `docs/cursor-tasks/phase4c-photo-gallery-frontend.md`:

````markdown
# Cursor Task: Phase 4C — Photo Gallery UI

## Context

Project: Joggy-PicX — Internal Dashboard for running event photo management.
Working directory: `apps/frontend/`
Stack: Next.js 15 App Router, TypeScript strict, TanStack Query v5, Tailwind CSS v4.

Backend API is live:
```
GET /internal/events/{event_id}/photos
  ?page=1&per_page=24&bib=&checkpoint_id=&ai_status=

Response: {
  items: PhotoItem[],
  total: number,
  page: number,
  per_page: number,
  pages: number
}
```

Auth pattern: use `apiGet` helper from `lib/api.ts` which auto-injects Supabase JWT.

Existing hooks:
- `hooks/useEvents.ts` — `useEvents()` — event list
- `hooks/useEventDetail.ts` — `useEventDetail(eventId)` — event detail including checkpoints
- `hooks/useReviewQueue.ts` — reference for hook pattern

## API Types

```typescript
type PhotoItem = {
  photo_id: string
  bib_number: string | null
  bib_confidence: number | null  // 0.0–1.0 or null
  ai_review_status: "auto" | "manual_pending" | "manual_approved" | "manual_rejected"
  thumbnail_url: string | null
  checkpoint_name: string | null
  captured_at: string | null
}

type EventPhotosResponse = {
  items: PhotoItem[]
  total: number
  page: number
  per_page: number
  pages: number
}
```

## Task A: Create `hooks/useEventPhotos.ts`

```typescript
"use client"
import { useQuery } from "@tanstack/react-query"
import { apiGet } from "../lib/api"

export type { PhotoItem }  // re-export the type above

type PhotoFilters = {
  page?: number
  bib?: string
  checkpointId?: string
  aiStatus?: string
}

async function getEventPhotos(
  eventId: string,
  filters: PhotoFilters
): Promise<EventPhotosResponse> {
  const params = new URLSearchParams()
  params.set("page", String(filters.page || 1))
  params.set("per_page", "24")
  if (filters.bib) params.set("bib", filters.bib)
  if (filters.checkpointId) params.set("checkpoint_id", filters.checkpointId)
  if (filters.aiStatus) params.set("ai_status", filters.aiStatus)

  const result = await apiGet<EventPhotosResponse>(
    `/internal/events/${eventId}/photos?${params.toString()}`
  )
  if (!result.success) throw new Error(result.error || "Failed to fetch photos")
  return result.data!
}

export function useEventPhotos(eventId: string | null, filters: PhotoFilters = {}) {
  return useQuery({
    queryKey: ["event-photos", eventId, filters],
    queryFn: () => getEventPhotos(eventId!, filters),
    enabled: !!eventId,
    staleTime: 30 * 1000,
  })
}
```

## Task B: Create `app/(internal)/dashboard/events/[id]/photos/page.tsx`

This is a full gallery page for browsing an event's photos.

### URL State

Use Next.js `useSearchParams` + `useRouter` + `useParams` to persist filter state in the URL.

- `page` (default `"1"`)
- `bib` (default `""`)
- `checkpoint_id` (default `""`)
- `ai_status` (default `""`)

When any filter changes, call `router.push` with updated search params and reset `page` to `1`.

### Layout

```
[← กลับ Event Detail]
h1: "ภาพถ่าย"  subtext: (loaded from useEventDetail)

Filter bar:
  [🔍 input: ค้นหาบิบ...]  [select: Checkpoint ▼]  [select: AI Status ▼]  [ล้าง filter button]

Stats: "แสดง X–Y จาก Z รูป"

Grid: 3 cols on mobile, 4 cols on md+

Pagination bar (at bottom)
```

### Filter bar details

- **Bib input**: `<input type="text" placeholder="ค้นหาบิบ...">` — debounce 300ms using `useEffect` + `setTimeout`
- **Checkpoint select**: `<select>` populated from `useEventDetail(eventId).data?.checkpoints` — first option is "ทุกจุด" (value `""`)
- **AI Status select**: `<select>` with hardcoded options:
  - `""` → "สถานะทั้งหมด"
  - `"auto"` → "✅ AI อนุมัติ"
  - `"manual_pending"` → "⏳ รอตรวจสอบ"
  - `"manual_approved"` → "✓ Staff อนุมัติ"
  - `"manual_rejected"` → "✗ Staff ปฏิเสธ"
- **ล้าง filter**: show only when any filter is active — resets all filters + page to defaults

### Photo Card (inline component)

Each photo card in the grid:

```tsx
// Card structure (Tailwind):
<div className="bg-white rounded-lg overflow-hidden shadow hover:shadow-md transition-shadow cursor-pointer">
  {/* Thumbnail */}
  <div className="aspect-square bg-slate-100 relative">
    {thumbnail_url ? (
      <img src={thumbnail_url} alt="photo" className="w-full h-full object-cover"
           onClick={() => setLightboxUrl(thumbnail_url)}
           onError={...fallback to 📷} />
    ) : (
      <div className="w-full h-full flex items-center justify-center text-4xl">📷</div>
    )}
  </div>
  {/* Info */}
  <div className="p-2 space-y-1">
    <div className="flex items-center justify-between">
      <span className="font-medium text-sm">{bib_number || "ไม่พบ"}</span>
      <ConfidenceBadge confidence={bib_confidence} />
    </div>
    <AIStatusBadge status={ai_review_status} />
    {checkpoint_name && <p className="text-xs text-slate-500">{checkpoint_name}</p>}
  </div>
</div>
```

**ConfidenceBadge**: `bib_confidence >= 0.70` → green, `0.50–0.69` → yellow, `< 0.50 or null` → red/grey. Show percentage or "—".

**AIStatusBadge**:
- `auto` → small green badge "✅ AI"
- `manual_pending` → yellow "⏳ รอ"
- `manual_approved` → green "✓ อนุมัติ"
- `manual_rejected` → red "✗ ปฏิเสธ"

### Loading State

Show 8 skeleton cards (grey `animate-pulse` squares, same grid).

### Empty State

When `items.length === 0` (after loading): "ไม่พบรูปภาพ" + show "ล้าง filter" button if filters active.

### Lightbox

Same pattern as Review Queue — `lightboxUrl: string | null` local state. Fixed overlay, `<img>`, backdrop click closes.

### Pagination Bar

```tsx
// Show: ← [1] [2] [3] ... [N] →
// Current page has different styling
// Disable ← when page=1, disable → when page=pages
```

Only show page numbers 1, 2, 3, ..., if many pages show ellipsis. Simple approach: show at most 7 page buttons (first, last, current ±2, ellipsis).

### State

Local React state only:
- `lightboxUrl: string | null`
- `bibInput: string` — raw input value (before debounce)

URL search params handle all other state (page, bib, checkpoint_id, ai_status).

## Task C: Add "ดูรูปภาพ" link in event detail page

File: `apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx`

Add a link button near the top of the page (after the event name heading, before checkpoints section):

```tsx
import Link from "next/link"

// Inside the rendered event detail (after the event name/status):
<Link
  href={`/dashboard/events/${eventId}/photos`}
  className="inline-flex items-center gap-2 px-4 py-2 bg-sky-600 text-white rounded-lg hover:bg-sky-700 text-sm font-medium"
>
  📷 ดูรูปภาพ
</Link>
```

## TypeScript Requirements

- No `any` types
- All props and state must be explicitly typed
- Export `PhotoItem` and `EventPhotosResponse` types from `useEventPhotos.ts`

## Commit

After implementing Tasks A, B, and C:

```bash
git add apps/frontend/hooks/useEventPhotos.ts \
        apps/frontend/app/(internal)/dashboard/events/[id]/photos/page.tsx \
        apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx
git commit -m "feat(frontend): Photo Gallery page — grid + filter + pagination + lightbox"
```
````

- [ ] **Step 2: Commit the Cursor prompt**

```bash
git add docs/cursor-tasks/phase4c-photo-gallery-frontend.md
git commit -m "docs(cursor): Phase 4C photo gallery frontend prompt"
```

- [ ] **Step 3: Run Cursor with the prompt**

Open Cursor IDE, navigate to `apps/frontend/`, and run:
```
Use the prompt at docs/cursor-tasks/phase4c-photo-gallery-frontend.md
```

- [ ] **Step 4: After Cursor completes — TypeScript check**

```bash
cd apps/frontend
npx tsc -p tsconfig.json --noEmit
```

Expected: `0 errors`

---

## Task 4: Update PROGRESS.md + CHANGELOG.md

**Files:**
- Modify: `PROGRESS.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update PROGRESS.md**

In PROGRESS.md Phase 4 section, mark Photo Gallery as complete.

- [ ] **Step 2: Update CHANGELOG.md**

Add under `[Unreleased]`:
- `[Claude] feat(api): GET /internal/events/{id}/photos — paginated gallery (bib/checkpoint/status filter, 6 TDD tests)`
- `[Cursor] feat(frontend): Photo Gallery page — 4-col grid, debounced filter, pagination, lightbox`

- [ ] **Step 3: Commit**

```bash
git add PROGRESS.md CHANGELOG.md
git commit -m "docs: Phase 4C Photo Gallery complete"
```
