# Cursor Task — ADR-0008 Phase B4: Multi-bib Photo Gallery UI

> Status: Ready for Cursor
> Author: Claude (Tech Lead)
> Date: 2026-06-05
> Related: ADR-0008 (`docs/adr/0008-multi-bib-pipeline.md`), GitHub Issue #1
> Backend already shipped: commits `5a27c7e` (Phase A) + `4dd179f` (Phase B)

---

## Context (read first)

The backend AI pipeline used to assume **1 bib per photo**. As of commit
`4dd179f` the API now returns **every bib detected in each photo** through a
new `bibs: BibOut[]` array on `PhotoItem`. Each entry has the detected
bib_number, OCR confidence, and the bounding box coordinates in the original
image's pixel space.

The legacy `bib_number` + `bib_confidence` fields are still populated with the
**highest-confidence bib** for backward compatibility — you can keep using
them where it makes sense, but the gallery should now show all bibs so a
runner appearing in a group photo can find themselves.

### Why this matters

Holdout test (2026-06-05) on 20 unseen photos:
- 20/20 photos had ≥ 1 bib
- **78 total bibs detected** (avg **3.9 per photo**, max **11 bibs** in one frame)

Showing only the top-1 bib means most secondary runners can't find their photos.

---

## Scope

Three files to touch:

1. **`apps/frontend/hooks/useEventPhotos.ts`** — add `BibOut` type + `bibs` field
2. **`apps/frontend/app/(internal)/dashboard/events/[id]/photos/page.tsx`** —
   show all bibs on each card + overlay boxes in the lightbox
3. *(optional)* a small reusable `<BibBadgeList>` component if it cleans up
   the card

Do **NOT** touch the backend, schemas, or any tests under `apps/backend/`.

---

## Task 1 — Update types in `useEventPhotos.ts`

Add a `BibOut` type matching the backend Pydantic model and extend `PhotoItem`:

```ts
export type BibOut = {
  bib_number: string;
  confidence: number;   // 0.0 - 1.0 (from OCR, not YOLO)
  bbox_x1: number;      // bounding box in ORIGINAL image pixel space
  bbox_y1: number;
  bbox_x2: number;
  bbox_y2: number;
};

export type PhotoItem = {
  photo_id: string;
  bib_number: string | null;        // DEPRECATED — best bib only; use `bibs` instead
  bib_confidence: number | null;    // DEPRECATED
  bibs: BibOut[];                   // NEW — sorted by confidence desc, may be empty
  ai_review_status: "auto" | "manual_pending" | "manual_approved" | "manual_rejected";
  thumbnail_url: string | null;
  checkpoint_name: string | null;
  captured_at: string | null;
};
```

Backend always sends `bibs` as a list (possibly empty); make the field
non-optional in TS so we don't have to null-check it everywhere.

---

## Task 2 — Update `PhotoCard` in `events/[id]/photos/page.tsx`

The current card shows only `photo.bib_number`. Replace that line with a list
of every bib in `photo.bibs`. Suggested UI:

```tsx
<div className="flex items-center justify-between gap-2 flex-wrap">
  {photo.bibs.length === 0 ? (
    <span className="font-medium text-sm text-slate-400">ไม่พบ</span>
  ) : (
    <div className="flex flex-wrap gap-1">
      {photo.bibs.slice(0, 4).map((b) => (
        <span
          key={b.bib_number + b.bbox_x1}
          className="px-1.5 py-0.5 text-xs font-medium rounded bg-slate-100 text-slate-700"
          title={`confidence ${(b.confidence * 100).toFixed(0)}%`}
        >
          {b.bib_number}
        </span>
      ))}
      {photo.bibs.length > 4 && (
        <span className="text-xs text-slate-500">+{photo.bibs.length - 4}</span>
      )}
    </div>
  )}
  <ConfidenceBadge confidence={photo.bib_confidence} />
</div>
```

Keep `ConfidenceBadge` showing the best-bib confidence (from the deprecated
field) — it's a useful summary signal even with the new list. Don't render it
when `photo.bibs.length === 0`.

The `key` deliberately combines `bib_number + bbox_x1` because the same bib
number could in theory appear twice in one photo (two photographers each
holding a print of the same number) — using `bib_number` alone would warn.

---

## Task 3 — Bib bbox overlay in the lightbox

The existing lightbox just shows the thumbnail in a modal. Add an overlay:
when the user opens a photo, draw a green rectangle around each bib with the
number printed in the top-left corner of the box.

### How to scale bboxes correctly

Bboxes are in **original image pixel space** (not thumbnail space), and we
display the image responsively with CSS. Use absolute positioning relative to
the `<img>` element, sized as a percentage of the displayed image — that way
the boxes stay locked to the bibs regardless of viewport size.

To do this we need the natural width/height of the image. Read it from the
`onLoad` event of the img and store in state:

```tsx
function Lightbox({ photo, onClose }: { photo: PhotoItem; onClose: () => void }) {
  const [imgSize, setImgSize] = useState<{ w: number; h: number } | null>(null);

  if (!photo.thumbnail_url) return null;
  return (
    <div
      role="dialog"
      className="fixed inset-0 bg-black/80 flex items-center justify-center z-50 touch-none"
      onClick={onClose}
    >
      <div className="relative max-w-[95vw] max-h-[95vh]" onClick={(e) => e.stopPropagation()}>
        <img
          src={photo.thumbnail_url}
          alt="photo"
          className="max-w-[95vw] max-h-[95vh] object-contain block"
          onLoad={(e) => {
            const el = e.currentTarget;
            setImgSize({ w: el.naturalWidth, h: el.naturalHeight });
          }}
        />
        {imgSize && photo.bibs.map((b) => {
          // Convert pixel coords to percentages of the natural image size.
          // CSS positions the overlay over the rendered img (which is sized
          // by object-contain), and percentages stay correct under any resize.
          const left = (b.bbox_x1 / imgSize.w) * 100;
          const top = (b.bbox_y1 / imgSize.h) * 100;
          const width = ((b.bbox_x2 - b.bbox_x1) / imgSize.w) * 100;
          const height = ((b.bbox_y2 - b.bbox_y1) / imgSize.h) * 100;
          return (
            <div
              key={b.bib_number + b.bbox_x1}
              className="absolute border-2 border-green-400 pointer-events-none"
              style={{
                left: `${left}%`,
                top: `${top}%`,
                width: `${width}%`,
                height: `${height}%`,
              }}
            >
              <span className="absolute -top-5 left-0 px-1 text-xs font-medium bg-green-400 text-black rounded-sm">
                {b.bib_number}
              </span>
            </div>
          );
        })}
        <button
          onClick={onClose}
          className="absolute top-2 right-2 bg-white/90 rounded-full w-8 h-8 flex items-center justify-center hover:bg-white"
          aria-label="Close"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
```

### Caveat about thumbnails

The backend serves a thumbnail URL whose pixel dimensions are smaller than
the original. The bbox is in **original** image pixel space, but the
percentages above use the rendered img's natural size — which IS the
thumbnail's natural size, not the original. The math still works as long as
the **thumbnail is a uniform scale-down of the original** (which it is — see
`apps/backend/joggy/services/thumbnail.py`, which preserves aspect ratio).
Just trust it, no manual scale factor needed.

If you ever fetch the original URL instead, the same math works because the
percentages are relative to whichever image's natural size you load.

---

## Visual reference

Right now the gallery looks like a normal photo grid. After this task each
card should show:

```
┌─────────────┐
│  [photo]    │
├─────────────┤
│ 1234 5678   │ ← list of bib pills (max 4 + "+N")
│ ✓ auto      │
│ กม.5         │
└─────────────┘
```

And clicking it opens a lightbox with green boxes around every bib.

---

## Acceptance criteria

- [ ] `BibOut` type added, `bibs` field added to `PhotoItem` (non-optional)
- [ ] Card shows all bib numbers (max 4 visible + "+N" for the rest)
- [ ] Card shows "ไม่พบ" when `bibs` is empty (don't render the confidence
      badge in that case)
- [ ] Lightbox draws a green bbox around every bib, with the number printed
      at the top-left of the box
- [ ] Boxes stay aligned to the bibs when the browser resizes (use
      percentages, not pixels)
- [ ] No TypeScript errors (`pnpm typecheck` or `tsc --noEmit` clean)
- [ ] No console errors when navigating to
      `/dashboard/events/<event_id>/photos` with mock data

---

## Out of scope (don't do these)

- Don't change the search input — bib filtering already works server-side
  (backend uses EXISTS on `photo_bibs.bib_number`).
- Don't add a review-queue UI for multi-bib here. The review queue endpoints
  haven't been updated yet (separate task).
- Don't touch the public/partner-facing pages.

---

## Manual test plan

1. `pnpm dev` and open `/dashboard/events/<any-event>/photos`.
2. Card shows all bib numbers as pills.
3. Click a photo — green boxes appear over the bibs in the lightbox.
4. Resize the browser — boxes stay locked to the bibs.
5. Find a photo where `bibs` is empty — card shows "ไม่พบ" without crashing.

When done, commit with a message like:

```
feat(frontend): ADR-0008 Phase B4 — multi-bib gallery + bbox overlay

- Add BibOut type and bibs field to PhotoItem
- Show all bib numbers (max 4 + "+N") on each photo card
- Lightbox draws green bbox + number label for every detected bib
- Bboxes positioned as percentages so they stay locked on resize

Closes ADR-0008 Phase B4. Backend already shipped in 4dd179f.
```
