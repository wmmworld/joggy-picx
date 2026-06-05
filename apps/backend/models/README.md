# ONNX Model Files

These files are NOT committed to git (see `.gitignore`).
Populate this directory before running `docker build` for the worker, or
before running `python tools/train/test_holdout.py` for a local sanity
check.

If any file is missing, `joggy.ai.session.load_sessions()` raises a
`FileNotFoundError` listing exactly which ones — the worker fails fast
at startup instead of serving traffic with broken inference.

## Required files

| File | Size | Source |
|------|------|--------|
| `yolov8n_bib.onnx` | ~12 MB | **v1 trained on Joggy dataset (see below)** |
| `ocr_det.onnx` | ~5 MB | Run `python tools/export/export_ocr.py` |
| `ocr_rec.onnx` | ~5 MB | Run `python tools/export/export_ocr.py` |
| `buffalo_s/det_10g.onnx` | ~5 MB | Download from InsightFace (see below) |
| `buffalo_s/w600k_r50.onnx` | ~100 MB | Download from InsightFace (see below) |

## yolov8n_bib.onnx — v1 (2026-06-05)

**Trained on:** Roboflow workspace `wmm-qv1ad` project `joggy-bib`
version 1 — 9,397 images (train 9,276 / val 76 / test 45, 640×640
stretch resize, 3× augmentation, single class `bib` merged from 6
source datasets — 4 public from Roboflow Universe + Thai marathon
photos annotated with SAM3 auto-label + manual review).

**Trainer:** YOLOv8-nano, 100 epochs, batch=16, imgsz=640, patience=20,
optimizer AdamW (auto), Kaggle Tesla T4 ×2.

**Held-out validation metrics (Roboflow split):**
- mAP50 = **0.914**
- mAP50-95 = 0.675
- precision ~ 0.91
- recall ~ 0.85

**CEO eyeball test (20 holdout photos never seen in training):**
- 20/20 images had ≥ 1 bib detected
- 78 total bibs detected (avg 3.9/image, max 11)
- Known v1 limitations: bibs occluded by hands/phones, bibs farther
  than ~20px in original image. Tracked as backlog "Bib detector v2
  hard cases" (see PROGRESS.md).

### To regenerate from scratch

1. Open Roboflow project `wmm-qv1ad/joggy-bib` (need access)
2. Download v1 dataset in YOLOv8 format (or run new training notebook)
3. Train on Kaggle: `tools/train/train_bib_colab.ipynb` (also works on
   Kaggle T4 with minor cell edits — see PROGRESS.md 2026-06-05 entry
   for what bit us when Colab GPU quota ran out)
4. Export to ONNX on Kaggle (faster than installing torch locally):
   ```python
   from ultralytics import YOLO
   YOLO("/kaggle/working/runs/.../weights/best.pt").export(
       format="onnx", imgsz=640, simplify=True, opset=17,
   )
   ```
5. Download `best.onnx`, rename to `yolov8n_bib.onnx`, drop here.

### Sanity check before deploy

```bash
python tools/train/test_holdout.py
```

Runs the production `BibDetector` class (D-021 onnxruntime-only) against
`joggy_dataset/holdout/`. Writes annotated copies with green bboxes to
`joggy_dataset/holdout_detected/` so you can eyeball them.

## Download InsightFace buffalo_s

```bash
pip install insightface
python -c "
import insightface
model = insightface.app.FaceAnalysis(name='buffalo_s', root='.')
model.prepare(ctx_id=-1)
# Files will be in ~/.insightface/models/buffalo_s/
"
cp ~/.insightface/models/buffalo_s/det_10g.onnx apps/backend/models/buffalo_s/
cp ~/.insightface/models/buffalo_s/w600k_r50.onnx apps/backend/models/buffalo_s/
```
