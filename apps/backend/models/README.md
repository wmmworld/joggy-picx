# ONNX Model Files

These files are NOT committed to git (see .gitignore).
Populate this directory before running `docker build` for the worker.

## Required files

| File | Size | Source |
|------|------|--------|
| `yolov8n_bib.onnx` | ~6 MB | Run `python tools/export/export_yolo.py` |
| `ocr_det.onnx` | ~5 MB | Run `python tools/export/export_ocr.py` |
| `ocr_rec.onnx` | ~5 MB | Run `python tools/export/export_ocr.py` |
| `buffalo_s/det_10g.onnx` | ~5 MB | Download from InsightFace (see below) |
| `buffalo_s/w600k_r50.onnx` | ~100 MB | Download from InsightFace (see below) |

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
