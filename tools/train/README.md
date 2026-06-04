# Train Bib Detector — Step-by-Step Guide (CEO Walkthrough)

This guide takes you from "10,000 marathon photos in a folder somewhere"
to "fine-tuned bib detection model live in production." Estimated CEO time:
**~5 hours over 2 days** (mostly annotation, can be paused/resumed).

Read the design spec first: [`docs/superpowers/specs/2026-06-04-bib-finetune-design.md`](../../docs/superpowers/specs/2026-06-04-bib-finetune-design.md)

---

## What you need before starting

- [ ] A folder of past marathon photos (10K+ images — yes, you have this)
- [ ] Google account (for Drive + Colab)
- [ ] Roboflow account (free tier — sign up at https://roboflow.com)
- [ ] About 5 hours of clock time spread across 1-2 days

You do NOT need:
- A GPU on your laptop (Colab provides one free)
- Any Python knowledge (notebook runs end-to-end with "Run All")
- ML expertise (the design spec already made all the technical choices)

---

## Part 1 — Pick 200 photos from your archive (~60 min)

Open your photo archive (Lightroom / Photos / Windows Explorer — whatever you use).

### What to pick (200 images target)

Aim for **diverse**, not just "high quality":

| Dimension | Target distribution |
|---|---|
| Angle | 40% front / 30% three-quarter / 20% side / 10% back |
| Distance | 30% full body / 50% half body / 20% close-up of bib |
| Lighting | 40% midday / 30% golden hour / 30% shade or indoor finish line |
| Crowd | 50% solo runner / 30% small group (2-3) / 20% dense pack (5+) |
| Tricky cases | 10-20 of: bent bibs, sweat/water on bib, backlit, low light |

### What to AVOID

- Burst-mode duplicates (if you took 5 nearly-identical shots, pick the best 1)
- Bibs cropped out of frame (top or bottom cut off)
- No-person images (start line empty, etc.)
- Severely motion-blurred (can't read the number → can't train)

### Export

- File format: **JPEG**
- Max long edge: **1600 px** (Roboflow auto-resizes to 640 anyway; smaller = faster upload)
- Save to a folder, e.g. `D:\joggy_dataset\thai_bib_v1\`
- **Set aside 20 of those 200** into a separate folder `holdout/` — these will be your acceptance test set, NEVER annotated/trained on. Pick variety here too.

You should end up with:
```
D:\joggy_dataset\thai_bib_v1\          (180 images — will go to Roboflow training)
D:\joggy_dataset\holdout\              (20 images — will stay local for final eval)
```

---

## Part 2 — Roboflow setup (~15 min)

### 2.1 Create workspace + project

1. Sign in at https://app.roboflow.com
2. Create a new **Workspace** if you don't have one (free tier: 1 workspace)
3. Click **Create New Project**:
   - Project Name: `joggy-bib`
   - License: `Private`
   - Project Type: **Object Detection**
   - What are you detecting: `bib`

### 2.2 Import public datasets

Roboflow Universe is a marketplace of free datasets.

1. Go to https://universe.roboflow.com
2. Search: `race bib`, `marathon bib`, or `running bib`
3. For each promising dataset:
   - Click in, look at the sample images
   - Are bibs labeled? Reasonable bounding boxes?
   - If yes: click **Download** → choose **YOLOv8 format** → click **Show download code**
   - Choose **"Add to existing project"** → select `joggy-bib`
4. Aim to add **2-3 public datasets** totaling 500+ images
5. **Important:** After import, go to Annotate → check that bib labels are
   correctly placed. Skip any dataset where >20% of labels look wrong.

### 2.3 Upload your Thai photos

1. In Roboflow project `joggy-bib` → click **Upload**
2. Drag your `D:\joggy_dataset\thai_bib_v1\` folder (180 images)
3. **DO NOT** upload the `holdout/` folder — those stay separate

After upload, all 180 Thai images will be in the "Unassigned" state, waiting
for annotation.

---

## Part 3 — Annotate your Thai photos (~3 hours, can split across days)

This is the only slow part. There's no shortcut — quality matters.

### How to annotate

1. In Roboflow project → click **Annotate** → click on the first unassigned image
2. Press `b` to start drawing a bounding box (or click the rectangle tool)
3. Click and drag tightly around each visible bib
4. Press `1` (or click `bib`) to assign the class
5. Press `→` to go to next image
6. Save automatically after each box

### Annotation tips

- **Tight boxes:** don't include too much margin around the bib
- **Every visible bib in the image:** even small/distant ones, even if partially occluded
- **Don't label cropped bibs:** if more than half the bib is outside the image, skip it
- **Take breaks:** annotation fatigue → sloppy labels → bad model. 30 images at a time.

You can pause and come back any time. Roboflow saves progress automatically.

### Estimated time

About **1 minute per image** if you're focused. 180 images = **3 hours** with breaks.

---

## Part 4 — Generate dataset version + export (~5 min)

After all 180 are annotated:

1. In Roboflow → click **Generate** in the left sidebar
2. **Preprocessing:** keep defaults (Auto-Orient + Resize 640×640)
3. **Augmentations** — add these to expand your training data:
   - Rotation: ±15°
   - Brightness: ±20%
   - Mosaic: enabled (combines 4 images — great for small object detection)
   - Output: 3 augmented versions per source image
4. **Train/Test Split:**
   - Train: 80%
   - Valid: 20%
   - Test: 0% (we use our own holdout outside Roboflow)
5. Click **Create**
6. Wait for generation (~2-5 min)
7. Click **Export Dataset** → choose **YOLOv8** format → click **Continue** → **Download zip**

Save the zip somewhere you can find it. We'll upload it to Drive next.

---

## Part 5 — Upload to Drive + train in Colab (~30-60 min wall clock)

### 5.1 Upload dataset to Google Drive

1. Open https://drive.google.com
2. Create a folder: `joggy-bib/`
3. Upload your exported zip → rename it to `dataset.zip`
4. Path should be: `/MyDrive/joggy-bib/dataset.zip`

### 5.2 Open the Colab notebook

1. Open `tools/train/train_bib_colab.ipynb` from the repo
2. Click **"Open in Colab"** button (or go to https://colab.research.google.com → File → Upload notebook)
3. **CRITICAL:** Runtime → Change runtime type → Hardware accelerator: **T4 GPU**
4. Runtime → **Run all** (Ctrl+F9)
5. When prompted to mount Drive → click the link, sign in, paste the code

### 5.3 Wait

- **Setup + unpack:** ~2 minutes
- **Training:** 30-60 minutes (GPU does the work; you can leave the tab open and go for coffee)
- **Export ONNX + copy to Drive:** ~1 minute

Watch the **results.png** chart at the end — you want mAP50 curves to plateau
high (≥0.85) and val loss to keep decreasing.

### 5.4 Download the trained model

1. Open Drive → `joggy-bib/output/`
2. Download `yolov8n_bib.onnx` (~6 MB)
3. Place it at `apps/backend/models/yolov8n_bib.onnx` in your repo

---

## Part 6 — Evaluate on holdout test (~5 min)

This proves the model works on photos it has never seen.

```bash
cd D:\Dev\Joggy-PicX

# Use a Python with onnxruntime + opencv installed (your backend venv works)
.venv\Scripts\python.exe tools/train/eval_bib.py `
    --model apps/backend/models/yolov8n_bib.onnx `
    --images D:\joggy_dataset\holdout\ `
    --conf 0.25
```

Read the output. You're looking for:
- **Recall ≥ 0.90** — model finds the bib in 90%+ of test images
- **Precision ≥ 0.80** — when it says "bib here", it's right 80%+ of the time
- **Inference < 1s per image** — fast enough for production

If thresholds pass → **commit the model** and restart backend worker — you're live!

If recall is low → collect 50-100 more "hard case" photos that the model
missed → add to Roboflow → re-export → re-run Colab → re-evaluate.

---

## Part 7 — Ship to production

1. The model file is in `.gitignore` (per `apps/backend/models/.gitignore`) so it won't be committed by accident.
2. Copy the model to your VPS / Hetzner manually:
   ```bash
   scp apps/backend/models/yolov8n_bib.onnx user@vps:/path/to/joggy/apps/backend/models/
   ```
3. Restart the worker container so it loads the new model:
   ```bash
   docker compose -f infra/docker-compose.yml restart worker
   ```
4. Process a few photos via Pi → check Review Queue starts showing detected bibs.

🎉 Done. Take a long bath.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| Colab says "no GPU available" | Runtime → Change runtime type → T4 GPU. Free tier sometimes has waits, retry after 10 min. |
| `data.yaml` not found | Your Roboflow export wasn't YOLOv8 format. Re-export with "YOLOv8" specifically. |
| Training mAP stays at 0 | Labels are wrong/empty. Check Roboflow annotation — did you assign the `bib` class? |
| `eval_bib.py` says "no holdout labels" | You forgot to annotate the holdout images. They need labels too (use Roboflow in a separate project, or annotate manually using a small script). |
| Recall < 0.85 after retraining twice | Dataset diversity issue. Look at which images the model misses — they're probably a class of images underrepresented in training (e.g., all dark photos). Add 30-50 similar ones to Roboflow + retrain. |
| ONNX inference much slower than 1s | Try `imgsz=416` instead of 640 in `tools/export/export_yolo.py` — trades a bit of accuracy for speed. |
