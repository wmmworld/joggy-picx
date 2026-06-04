# Bib Detection Fine-tune — Design Spec

**Date:** 2026-06-04
**Owner:** Claude (Tech Lead) + CEO (annotation)
**Phase:** 6 (post-Phase-5 polish)
**Status:** Approved — implementation pending CEO dataset

---

## Goal

Train a 1-class YOLOv8-nano model that detects race-bibs (rectangular number plates on runners' chests/torsos) in Canon EOS RP photos taken at Thai marathon events.

**Output artifact:** `apps/backend/models/yolov8n_bib.onnx` — drop-in replacement for the COCO-pretrained `yolov8n.onnx` currently expected by `apps/backend/joggy/ai/bib_detector.py`.

**Why this exists:** Phase 3 wired the whole AI pipeline (detect → OCR → review queue) but used a generic COCO YOLO that has no "bib" class. AI Review Queue currently has no signal to act on. This spec unblocks production AI.

---

## Success criteria

Run the trained model on a 20-image holdout of Thai marathon photos that the model has never seen during training:

| Metric | Target | Why |
|---|---|---|
| Recall @ IoU 0.5 | ≥ 0.90 | False negatives → runners not found in dashboard search; very bad UX |
| Precision @ IoU 0.5 | ≥ 0.80 | False positives → OCR runs on non-bibs, fills review queue with noise |
| mAP50 | ≥ 0.85 | Industry-standard summary |
| Inference time (Hetzner CPX11 CPU) | < 1s per 4MP image | Real-time pipeline budget |
| Model size | < 10 MB ONNX | RAM budget per D-021 |

If recall < 0.90 → expand Thai supplemental dataset, retrain. Do not ship to production until recall threshold is met.

---

## Dataset strategy — Hybrid

Decision made during brainstorm 2026-06-04 morning:

```
Public datasets (~500 images, Roboflow Universe)
    +
Thai marathon photos from CEO archives (~200 images, hand-annotated)
    =
Combined training set (~700 images, plus augmentation 3-5x → ~2000-3500)
```

**Holdout test set:** 20 Thai photos that the model has NEVER seen during training. Used only for the final acceptance metric. Picked by CEO from the same archive but stored separately, never imported to the training Roboflow project.

### Public datasets — research targets

CEO will search Roboflow Universe (https://universe.roboflow.com) for:
- Search term: `"race bib"`, `"marathon"`, `"running bib"`, `"bib number"`
- Filter: license = CC BY 4.0 or public domain
- Pick 2-3 datasets with combined >500 images, varied lighting/angles
- Reference: existing well-known dataset is the "RBNR" academic set (~217 images)

Specific datasets to try (verify availability before relying):
- "Race Bib Recognition" workspaces on Roboflow Universe (multiple authors)
- "Marathon Bib" datasets
- "Runner Bib Detection" projects

**Acceptance rule for a public dataset:** Look at 10 random images. If ≥ 8 of them have clearly-visible bibs and reasonable bounding boxes, keep it. Otherwise skip.

### Thai supplemental — selection checklist

CEO has 10,000+ photos from past marathon events. Cull down to ~200 using:

**Required (every image):**
- Bib clearly visible (not occluded by arm, phone, other runner)
- Not motion-blurred beyond reading the bib digits
- Reasonable contrast (bib distinguishable from shirt)

**Diversity (target distribution):**
- Angle: front 40% / 3-quarter 30% / side 20% / back 10%
- Distance: full-body 30% / half-body 50% / close-up 20%
- Lighting: midday 40% / golden hour 30% / shade/indoor 30%
- Bib design variety: keep at least 5 different bib styles
- Crowd density: solo 50% / small group 2-3 30% / dense group 5+ 20%

**Bonus tricky cases (10-20 images):**
- Bent / folded bibs
- Sweat / water on bib
- Backlit / silhouette
- Low light
- Partial occlusion (intentional, to teach edge cases)

**Avoid:**
- Burst-mode duplicates (pick 1 of 5)
- Cut bibs (top/bottom cropped out by frame)
- No-person images

Final 200 images → upload to Roboflow → annotate.

---

## Toolchain — Roboflow annotate + Colab train

Decision made during brainstorm. Reasoning:

| Choice | Why |
|---|---|
| **Roboflow** for annotate + dataset hosting | Free 500-image quota; built-in augmentation; YOLO export native; public dataset import 1-click; better annotation UI than CVAT |
| **Colab Free** for training | T4 GPU sufficient for yolov8n; 12-hour session limit; zero cost; notebook is shareable + versioned |
| **Roboflow → Drive → Colab → Drive** flow | Roboflow exports zip to local download; CEO uploads to Drive; Colab mounts Drive; trained model + ONNX saved back to Drive; CEO downloads + commits to repo |

**Vendor lock-in mitigation:** Roboflow exports raw YOLO-format labels (txt files with `class_id x_center y_center width height` per line). Compatible with any training framework. We export this format and never depend on Roboflow's hosted training feature.

**Upgrade path if Colab Free is too slow:**
- Colab Pro (~$10/month) — V100 GPU, longer sessions
- RunPod RTX 3090 spot (~$0.3/hr × 1hr = $0.30/run)
- Local GPU if CEO has one

---

## File structure produced by this spec

```
docs/superpowers/specs/2026-06-04-bib-finetune-design.md   # this file
tools/train/
  README.md                  # step-by-step for CEO (Roboflow → Colab → deploy)
  train_bib_colab.ipynb      # Colab notebook — runs end-to-end
  eval_bib.py                # local script — measure mAP on holdout test set
  datasets.md                # research notes on public datasets we tried
apps/backend/models/
  yolov8n_bib.onnx           # final trained model (NOT committed; in .gitignore)
```

---

## Workflow

```
1. CEO: pick 200 Thai photos    (~60 min)
2. CEO: Roboflow setup + import public dataset(s)  (~15 min)
3. CEO: upload Thai photos to Roboflow              (~5 min)
4. CEO: annotate 180 photos (skip 20 holdout)       (~3 hr — manual)
5. CEO: holdout 20 → separate folder, annotate too  (~30 min)
6. CEO: Roboflow generates dataset version          (~5 min)
       - 80/20 train/val split on the 180 annotated
       - augmentation: rotation ±15°, brightness ±20%, mosaic
       - export YOLO format → download zip
7. CEO: upload zip to Google Drive                  (~5 min)
8. CEO: open tools/train/train_bib_colab.ipynb in Colab
        runtime: T4 GPU
        run all cells → trains for ~30-60 min → saves best.onnx to Drive
9. CEO: download best.onnx → place in apps/backend/models/yolov8n_bib.onnx
10. Claude: run tools/train/eval_bib.py on 20 holdout images
            → metrics report
11. If metrics pass success criteria → ship to production
   If recall < 0.90 → CEO supplements with 50-100 more hard cases → retrain
```

Total CEO time: **~5 hours over a couple of days**, mostly annotation.
Total Claude time: **~30 min** to integrate model + verify.

---

## Risks + mitigations

| Risk | Mitigation |
|---|---|
| Public dataset bib design too different from Thai | Hybrid strategy already addresses — Thai supplemental dominates the fine-tune phase |
| Annotation inconsistency | Roboflow has class lock + bbox snap; one annotator (CEO) = consistent labels by definition |
| Colab session timeout mid-training | Use yolov8n (small model) + save checkpoints every epoch; resumable |
| ONNX export tensor shape mismatch | Use same export call as existing `tools/export/export_yolo.py` — output `[1, 5, 8400]` for 1-class is what `bib_detector.py` expects |
| Model overfits to Thai dataset | Hold 20 images out + augmentation; if train mAP >> val mAP, raise augmentation strength |
| Inference too slow on Hetzner CPX11 CPU | yolov8n at imgsz 640 benchmarks ~80ms on 4-core CPU; well within 1s budget. If issue: drop to imgsz 416 |

---

## What is NOT in scope of this spec

- Fine-tuning the OCR model (separate task; PaddleOCR is pretrained and adequate)
- Fine-tuning face embedding (InsightFace pretrained is adequate per D-021)
- Multi-class detection (e.g., separate "torso bib" vs "thigh bib") — keep it 1-class for v1
- Active learning loop (hard-example mining for v2 after first race)
- On-device inference (TFLite for mobile) — deferred per D-016

---

## Open decisions deferred to implementation

1. **Class name string:** `bib` vs `race_bib` vs `bib_number` — pick `bib` (shortest, what the existing code expects in label files)
2. **Image size at training:** `imgsz=640` (default) — try 832 only if recall is low on small/distant bibs
3. **Epochs:** start with 100 epochs; early-stop on validation mAP plateau
4. **Batch size:** auto (Colab T4 = ~16 for yolov8n at imgsz 640)
5. **Optimizer:** SGD default (ultralytics chooses sensible defaults; don't tune unless needed)
