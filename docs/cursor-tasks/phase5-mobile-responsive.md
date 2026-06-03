# Cursor Task: Mobile-Responsive UI Polish

## Context

Project: Joggy-PicX — Internal Dashboard
Working directory: `apps/frontend/`
Stack: Next.js 15 App Router, TypeScript strict, TanStack Query v5, Tailwind CSS v4

CEO uses this dashboard on a phone at marathon events to monitor photos arriving
from the Canon EOS RP camera. Currently the UI is desktop-only — needs to work
on mobile (375px–430px viewport) without breaking desktop layout.

**Primary use case on mobile:**
1. Check photo gallery — did the shot arrive?
2. Check event detail — event running?
3. Review queue — approve/reject borderline photos

**NOT required on mobile:** Edit modals, Create event (admin does this on desktop)

---

## Files to modify

1. `apps/frontend/app/layout.tsx` — add viewport meta tag
2. `apps/frontend/app/(internal)/dashboard/page.tsx` — main dashboard cards
3. `apps/frontend/app/(internal)/dashboard/events/page.tsx` — event list
4. `apps/frontend/app/(internal)/dashboard/events/[id]/page.tsx` — event detail
5. `apps/frontend/app/(internal)/dashboard/events/[id]/photos/page.tsx` — photo gallery (most important)
6. `apps/frontend/app/(internal)/dashboard/review/page.tsx` — review queue

---

## Task 1: `app/layout.tsx` — viewport meta

Add viewport meta so mobile browser doesn't zoom out:

```tsx
export const metadata = {
  title: "Joggy-PicX — Internal Dashboard",
  description: "Admin / Staff dashboard for Joggy-PicX"
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
};
```

---

## Task 2: `dashboard/page.tsx` — main dashboard

Current: `p-6` on outer div, cards work on mobile already (`grid-cols-1 md:grid-cols-2 lg:grid-cols-3`)

Changes:
- Outer div: `p-4 md:p-6` (reduce padding on mobile)
- Header: `text-2xl md:text-3xl` (smaller h1 on mobile)

---

## Task 3: `dashboard/events/page.tsx` — event list

Check and ensure:
- Table/list is readable on mobile (375px)
- "สร้างงาน" button is full-width or prominent on mobile
- Event name doesn't overflow

If current layout uses a table, convert to card-based list on mobile using responsive classes. Keep table on `md:` and above.

---

## Task 4: `dashboard/events/[id]/page.tsx` — event detail

Changes needed:
- Action buttons row: `flex flex-wrap gap-2` (buttons wrap on small screen, don't overflow)
- Event detail grid: `grid-cols-2 md:grid-cols-3` already works — verify on mobile
- Breadcrumb: shrink text on mobile with `text-sm`
- "📷 ดูรูปภาพ" button: ensure full-width readable on mobile

---

## Task 5: `dashboard/events/[id]/photos/page.tsx` — photo gallery (PRIMARY)

This is the most important page for mobile use.

### Filter bar
Current: `grid grid-cols-1 md:grid-cols-4 gap-3`
- Already collapses to 1 column on mobile ✅
- Make search input `text-base` on mobile to prevent iOS zoom (iOS zooms when input font-size < 16px)

### Photo grid
Current: `grid grid-cols-3 md:grid-cols-4 gap-4`

Change to:
```tsx
className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-2 md:gap-4"
```
- Mobile: 2 columns (photos large enough to tap)
- Tablet: 3 columns
- Desktop: 4 columns

### Photo card aspect ratio
Add `aspect-square` to the image container so cards are consistent height:
```tsx
<div className="aspect-square bg-slate-100 relative overflow-hidden">
  <Image ... className="w-full h-full object-cover" />
</div>
```

### Pagination bar
Current: Shows page numbers — on mobile show only Prev/Next + "หน้า X/Y":
```tsx
// Mobile: show only prev/next + page indicator
// md: show full pagination
<div className="flex items-center justify-center gap-2">
  <button>← ก่อน</button>
  <span className="text-sm text-slate-600">หน้า {page} / {totalPages}</span>
  <button>ถัดไป →</button>
</div>
```

Or simplest fix: just ensure current pagination doesn't overflow on mobile with `flex-wrap`.

### Lightbox
Current: `fixed inset-0` + `p-4` — works on mobile already ✅
Add `touch-action: none` class to prevent scroll-behind on iOS: `className="... touch-none"`

---

## Task 6: `dashboard/review/page.tsx` — review queue

Current has `overflow-x-auto` on the table — good for mobile scroll.

Changes:
- Stats bar: wrap with `flex-wrap` so badges wrap on small screens
- Event dropdown: `w-full md:w-96` — already done ✅
- Table: keep `overflow-x-auto` — users swipe horizontally
- Add `min-w-[600px]` to the table itself so columns don't collapse weirdly

---

## TypeScript Requirements

- No `any` types
- `npx tsc -p tsconfig.json --noEmit` must pass with 0 errors after changes

---

## Testing checklist

After changes, open browser DevTools → Toggle device toolbar → iPhone SE (375px):
- [ ] Dashboard: cards readable, no overflow
- [ ] Events list: readable
- [ ] Event detail: buttons wrap, not overflow
- [ ] Photo gallery: 2-col grid, images tap-able
- [ ] Review queue: horizontal scroll works
- [ ] Login page: form centered, inputs full-width

---

## Commit

```bash
git add apps/frontend/app/layout.tsx \
        apps/frontend/app/\(internal\)/dashboard/page.tsx \
        apps/frontend/app/\(internal\)/dashboard/events/page.tsx \
        apps/frontend/app/\(internal\)/dashboard/events/\[id\]/page.tsx \
        apps/frontend/app/\(internal\)/dashboard/events/\[id\]/photos/page.tsx \
        apps/frontend/app/\(internal\)/dashboard/review/page.tsx
git commit -m "feat(frontend): mobile-responsive UI — photo gallery 2-col, viewport meta, flex-wrap actions"
```
