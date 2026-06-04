# Public Bib Detection Datasets — Research Notes

Curated list of public race-bib datasets to use as the "public ~500 image"
half of our hybrid training set. Verify each link is live before importing —
Roboflow Universe projects come and go.

---

## How to search Roboflow Universe

URL: https://universe.roboflow.com

**Try these search terms** (best first):

1. `race bib detection`
2. `marathon bib`
3. `bib number`
4. `running bib`
5. `racing bib`
6. `RBNR` (the academic acronym for "Race Bib Number Recognition")

**Filters that help:**
- License: prefer **CC BY 4.0** or **Public Domain**
- Image count: ≥ 100 (smaller datasets aren't worth the import overhead)
- Most recent first (data quality has gone up over time)

---

## Quality acceptance rule

Before importing a dataset to your `joggy-bib` project, **look at 10 random
sample images** on the dataset's Roboflow page:

| Check | Pass condition |
|---|---|
| Are bibs labeled? | ≥ 8/10 images show bib bounding boxes |
| Are boxes tight? | Boxes hug the bib, not the whole torso |
| Is the class actually "bib"? | Some datasets label "person" instead — skip those |
| Reasonable diversity? | Not all the same race/lighting |

If a dataset passes → import. If not → skip and try another.

---

## Datasets to try (known good starting candidates)

These are search-result patterns, not stable URLs. Roboflow projects can be
deleted/renamed at any time. Spend ~10 min searching before commit:

### Tier 1 — academic / well-curated

- **RBNR (Race Bib Number Recognition) datasets** — original academic
  dataset from Computer Vision research. ~217 images, hand-labeled bibs.
  Search: `RBNR`. Multiple Roboflow re-uploads exist.

- **Marathon Photos** projects — community-uploaded subsets of various
  marathon photo agencies. Search: `marathon photos detection`.

### Tier 2 — community contributions

- Various **"race bib detection"** workspace projects — vary in quality;
  check sample images carefully.

- **"Running event"** datasets — sometimes labeled at person-level, but
  the visible bibs are usable as supervision once you re-annotate.

### Tier 3 — adjacent datasets (skip unless desperate)

- **License plate detection** — similar shape to bibs but different
  context; transfer learning might help but not directly useful as labels.

- **Number plate / sign detection** — too generic; skip.

---

## Combination strategy

Aim for **500+ images total from public sources**, mixed across 2-3 datasets:

| Total target | Per dataset | Why mix |
|---|---|---|
| 500-800 images | 200-400 each | Diversity > size; different cameras / lighting / bib designs |

Then your 180 Thai images (annotated) tip the balance toward real-world
distribution during training. With augmentation 3x, training set ends up
around **2,000-2,500 augmented samples** — comfortable for yolov8n on T4.

---

## What to do if Roboflow Universe disappoints

If you can't find ≥ 500 good public images:

**Option A — Increase Thai annotation effort**
Annotate 400-500 Thai images instead of 180. More time-consuming but data
matches production distribution perfectly. Skip public datasets entirely.

**Option B — Synthetic data**
Render fake bibs onto runners using image compositing. Tools like
"Domain Randomization" + Roboflow's built-in augmentation can fake it.
More work than annotation; only if Option A is impossible.

**Option C — Defer fine-tuning**
Ship with pretrained COCO yolov8n for v1; have Review Queue handle
everything. Build a real dataset from production photos over weeks.
Comes at the cost of slow review queue throughput initially.

---

## After import — generate dataset version

In your Roboflow project's `Generate` step:

- **Preprocess:** Auto-Orient + Resize 640×640 + Auto-Adjust Contrast
- **Augment:** Rotation ±15°, Brightness ±20%, Mosaic, Flip Horizontal
- **Outputs per source:** 3× augmented copies (free tier allows this)
- **Train/Valid:** 80/20 (skip Test — we hold out 20 Thai images locally)

Click Generate → wait → Export YOLOv8 → download zip → continue with the
Colab notebook per `tools/train/README.md`.
