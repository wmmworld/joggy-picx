#!/usr/bin/env python3
"""
Export YOLOv8-nano to ONNX for bib detection.
Run in DEV environment only — NOT in production.

Requirements (dev env, not in pyproject.toml):
    pip install ultralytics

Usage:
    python tools/export/export_yolo.py
    # Output: yolov8n.onnx → copy to apps/backend/models/yolov8n_bib.onnx

For fine-tuned model, replace "yolov8n.pt" with your weights path.
Verify output tensor names:
    import onnxruntime as ort
    s = ort.InferenceSession("apps/backend/models/yolov8n_bib.onnx")
    print(s.get_inputs()[0].name)   # should be "images"
    print(s.get_outputs()[0].name)  # should be "output0"
    print(s.get_outputs()[0].shape) # should be [1, 5, 8400] for 1-class model
"""
import shutil
from pathlib import Path

try:
    from ultralytics import YOLO
except ImportError:
    raise SystemExit("Run: pip install ultralytics")

MODEL_WEIGHTS = "models/best.pt"   # Kaggle-trained: mAP50=0.914, mAP50-95=0.675
OUTPUT_DIR = Path("apps/backend/models")

print(f"Loading {MODEL_WEIGHTS} ...")
model = YOLO(MODEL_WEIGHTS)

print("Exporting to ONNX (imgsz=640, simplify=True) ...")
model.export(format="onnx", imgsz=640, simplify=True, opset=17)

# Ultralytics writes best.onnx next to best.pt
src = Path("models/best.onnx")
dst = OUTPUT_DIR / "yolov8n_bib.onnx"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
shutil.move(str(src), str(dst))
print(f"Saved: {dst}")
print("Done. Verify tensor names before running worker.")
