#!/usr/bin/env python3
"""
Export PaddleOCR PP-OCRv4 det+rec to ONNX for bib OCR.
Run in DEV environment only — NOT in production.

Requirements (dev env):
    pip install paddlepaddle paddle2onnx

Steps:
1. Download PP-OCRv4 models from PaddleOCR:
   https://github.com/PaddlePaddle/PaddleOCR/blob/main/doc/doc_en/models_list_en.md
   - Det: ch_PP-OCRv4_det_infer.tar
   - Rec: ch_PP-OCRv4_rec_infer.tar

2. Run this script (or the commands below directly):

Usage:
    python tools/export/export_ocr.py

Output: apps/backend/models/ocr_det.onnx, apps/backend/models/ocr_rec.onnx

Verify:
    import onnxruntime as ort
    s = ort.InferenceSession("apps/backend/models/ocr_rec.onnx")
    print(s.get_inputs()[0].name)    # should be "x"
    print(s.get_outputs()[0].name)   # should be "softmax_0.tmp_0"
    print(s.get_outputs()[0].shape)  # should be [1, T, 11] for digit-only model
"""
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = Path("apps/backend/models")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def paddle2onnx_export(model_dir: str, save_file: str, input_shape: str) -> None:
    cmd = [
        sys.executable, "-m", "paddle2onnx",
        "--model_dir", model_dir,
        "--model_filename", "inference.pdmodel",
        "--params_filename", "inference.pdiparams",
        "--save_file", save_file,
        "--input_shape_dict", input_shape,
        "--opset_version", "11",
        "--enable_onnx_checker", "True",
    ]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


det_model_dir = "ch_PP-OCRv4_det_infer"
rec_model_dir = "ch_PP-OCRv4_rec_infer"

print("=== Exporting OCR detection model ===")
paddle2onnx_export(
    det_model_dir,
    str(OUTPUT_DIR / "ocr_det.onnx"),
    '{"x": [1, 3, 960, 960]}',
)

print("=== Exporting OCR recognition model ===")
paddle2onnx_export(
    rec_model_dir,
    str(OUTPUT_DIR / "ocr_rec.onnx"),
    '{"x": [1, 3, 48, 320]}',
)

print("Done. Verify tensor names before running worker.")
