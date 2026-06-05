#!/usr/bin/env python3
"""
Test BibDetector (ONNX) against holdout images.

ทดสอบ ONNX model ที่ export มาจาก Kaggle (joggy-bib-v1 best.pt)
กับรูป holdout 20 รูปที่ไม่เคยเห็นตอน train

Usage:
    cd D:/Dev/Joggy-PicX
    python tools/train/test_holdout.py

Requirements (production stack):
    onnxruntime, opencv-python-headless, numpy
"""
from __future__ import annotations

import sys
from pathlib import Path

import cv2
import onnxruntime as ort

# Make backend package importable without installing
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps" / "backend"))

from joggy.ai.bib_detector import BibDetector  # noqa: E402

MODEL_PATH = ROOT / "apps" / "backend" / "models" / "yolov8n_bib.onnx"
HOLDOUT_DIR = ROOT / "joggy_dataset" / "holdout"
OUTPUT_DIR = ROOT / "joggy_dataset" / "holdout_detected"


def main() -> int:
    if not MODEL_PATH.exists():
        print(f"[ERROR] Model not found: {MODEL_PATH}")
        print("   Export ONNX from Kaggle first, then copy to that path.")
        return 1

    print(f"Loading model: {MODEL_PATH}")
    session = ort.InferenceSession(str(MODEL_PATH), providers=["CPUExecutionProvider"])
    detector = BibDetector(session)

    # Verify ONNX tensor signature matches BibDetector expectations
    inp = session.get_inputs()[0]
    out = session.get_outputs()[0]
    print(f"  input  : name={inp.name!r}  shape={inp.shape}")
    print(f"  output : name={out.name!r}  shape={out.shape}")
    print()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    images = sorted(p for p in HOLDOUT_DIR.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if not images:
        print(f"[ERROR] No images in {HOLDOUT_DIR}")
        return 1

    images_with_bib = 0
    total_bibs = 0
    rows: list[tuple[str, str]] = []
    for img_path in images:
        img = cv2.imread(str(img_path))
        if img is None:
            rows.append((img_path.name, "READ-ERROR"))
            continue

        boxes = detector.detect_all(img)
        if not boxes:
            rows.append((img_path.name, "no bib"))
            continue

        images_with_bib += 1
        total_bibs += len(boxes)
        confs = ", ".join(f"{b.confidence:.2f}" for b in boxes)
        rows.append((img_path.name, f"{len(boxes)} bib(s)  conf=[{confs}]"))

        # Draw every box for visual review
        annotated = img.copy()
        for i, box in enumerate(boxes):
            cv2.rectangle(annotated, (box.x1, box.y1), (box.x2, box.y2), (0, 255, 0), 3)
            label = f"#{i+1} {box.confidence:.2f}"
            cv2.putText(annotated, label, (box.x1, max(0, box.y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        cv2.imwrite(str(OUTPUT_DIR / img_path.name), annotated)

    print(f"{'File':<35}  Result")
    print("-" * 80)
    for name, result in rows:
        print(f"{name:<35}  {result}")

    print()
    print(f"[OK] {images_with_bib}/{len(images)} images had >=1 bib ({images_with_bib / len(images):.1%})")
    print(f"     Total bibs detected: {total_bibs}  (avg {total_bibs / len(images):.2f} per image)")
    print(f"     Annotated images saved to: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
