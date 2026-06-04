#!/usr/bin/env python3
"""Evaluate a fine-tuned bib detection ONNX model on a holdout test set.

Loads the ONNX model with onnxruntime (same engine as production), runs
inference on each image, and computes precision/recall/mAP@0.5 against
hand-labeled ground truth.

Usage:
    python tools/train/eval_bib.py \
        --model apps/backend/models/yolov8n_bib.onnx \
        --images /path/to/holdout/images/ \
        --labels /path/to/holdout/labels/ \
        --conf 0.25 \
        --iou-match 0.5

If --labels is omitted, the script reports per-image detection counts and
mean inference time only (useful for sanity check, but no accuracy metrics).

Labels expected in YOLO format: one .txt per image, lines of
    class_id x_center y_center width height   (all normalized 0-1)

Exit code 0 if recall >= --recall-target and precision >= --precision-target.
Exit code 1 otherwise — suitable for CI gating.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort


# ── Inference helpers ─────────────────────────────────────────────────────────


def letterbox(img: np.ndarray, new_size: int = 640) -> tuple[np.ndarray, float, tuple[int, int]]:
    """Resize image to new_size x new_size while keeping aspect ratio.

    Returns (padded_image, scale_factor, (pad_left, pad_top)) so we can map
    detected boxes back to original coordinates.
    """
    h, w = img.shape[:2]
    scale = new_size / max(h, w)
    nh, nw = int(round(h * scale)), int(round(w * scale))
    resized = cv2.resize(img, (nw, nh), interpolation=cv2.INTER_LINEAR)

    pad_top = (new_size - nh) // 2
    pad_bottom = new_size - nh - pad_top
    pad_left = (new_size - nw) // 2
    pad_right = new_size - nw - pad_left

    padded = cv2.copyMakeBorder(
        resized, pad_top, pad_bottom, pad_left, pad_right,
        cv2.BORDER_CONSTANT, value=(114, 114, 114),
    )
    return padded, scale, (pad_left, pad_top)


def preprocess(img_path: Path, imgsz: int) -> tuple[np.ndarray, float, tuple[int, int], tuple[int, int]]:
    """Read image and convert to YOLOv8 input tensor.

    Returns (tensor, scale, padding, original_hw).
    """
    img = cv2.imread(str(img_path))
    if img is None:
        raise FileNotFoundError(f"Cannot read {img_path}")
    h0, w0 = img.shape[:2]
    padded, scale, padding = letterbox(img, imgsz)
    # BGR → RGB, HWC → CHW, scale 0-255 → 0-1, add batch dim
    rgb = cv2.cvtColor(padded, cv2.COLOR_BGR2RGB)
    tensor = rgb.transpose(2, 0, 1).astype(np.float32) / 255.0
    tensor = np.expand_dims(tensor, 0)
    return tensor, scale, padding, (h0, w0)


def postprocess(
    output: np.ndarray, scale: float, padding: tuple[int, int],
    orig_hw: tuple[int, int], conf_threshold: float, nms_iou: float,
) -> list[tuple[float, float, float, float, float]]:
    """Decode YOLOv8 1-class output [1, 5, 8400] into list of (x1,y1,x2,y2,conf).

    Coordinates are in ORIGINAL image space (not letterboxed).
    """
    # output shape: [1, 5, N] where 5 = [cx, cy, w, h, class0_conf]
    preds = output[0].T  # [N, 5]
    confs = preds[:, 4]
    keep = confs > conf_threshold
    preds = preds[keep]
    if len(preds) == 0:
        return []

    # cx,cy,w,h in letterboxed 640-space → x1,y1,x2,y2
    cx, cy, w, h = preds[:, 0], preds[:, 1], preds[:, 2], preds[:, 3]
    x1 = cx - w / 2
    y1 = cy - h / 2
    x2 = cx + w / 2
    y2 = cy + h / 2

    # Map back to original image space: undo padding + scale
    pad_left, pad_top = padding
    x1 = (x1 - pad_left) / scale
    y1 = (y1 - pad_top) / scale
    x2 = (x2 - pad_left) / scale
    y2 = (y2 - pad_top) / scale

    # Clip to image bounds
    h0, w0 = orig_hw
    x1 = np.clip(x1, 0, w0)
    y1 = np.clip(y1, 0, h0)
    x2 = np.clip(x2, 0, w0)
    y2 = np.clip(y2, 0, h0)

    # OpenCV NMS
    boxes = np.stack([x1, y1, x2 - x1, y2 - y1], axis=1).astype(np.float32)  # [N, 4] xywh
    scores = preds[:, 4].astype(np.float32)
    indices = cv2.dnn.NMSBoxes(boxes.tolist(), scores.tolist(), conf_threshold, nms_iou)
    if len(indices) == 0:
        return []
    indices = np.array(indices).flatten()
    return [(float(x1[i]), float(y1[i]), float(x2[i]), float(y2[i]), float(scores[i])) for i in indices]


# ── Ground truth loading ──────────────────────────────────────────────────────


def load_yolo_labels(label_path: Path, orig_hw: tuple[int, int]) -> list[tuple[float, float, float, float]]:
    """Load YOLO-format label file → list of (x1,y1,x2,y2) in original pixels."""
    if not label_path.exists():
        return []
    h, w = orig_hw
    boxes = []
    for line in label_path.read_text().strip().splitlines():
        parts = line.split()
        if len(parts) < 5:
            continue
        # class_id, x_center, y_center, width, height — all normalized
        _, cx, cy, bw, bh = parts[:5]
        cx, cy, bw, bh = float(cx) * w, float(cy) * h, float(bw) * w, float(bh) * h
        boxes.append((cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2))
    return boxes


def iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    """IoU between two (x1,y1,x2,y2) boxes."""
    inter_x1 = max(a[0], b[0])
    inter_y1 = max(a[1], b[1])
    inter_x2 = min(a[2], b[2])
    inter_y2 = min(a[3], b[3])
    if inter_x2 <= inter_x1 or inter_y2 <= inter_y1:
        return 0.0
    inter = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


# ── Main ──────────────────────────────────────────────────────────────────────


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True, type=Path, help="Path to ONNX model")
    p.add_argument("--images", required=True, type=Path, help="Directory of test JPEGs")
    p.add_argument("--labels", type=Path, default=None,
                   help="Directory of YOLO .txt labels (same basenames as images). "
                        "If omitted, only inference stats reported.")
    p.add_argument("--conf", type=float, default=0.25, help="Detection confidence threshold")
    p.add_argument("--iou-nms", type=float, default=0.45, help="IoU for NMS")
    p.add_argument("--iou-match", type=float, default=0.5, help="IoU for TP/FP matching against ground truth")
    p.add_argument("--imgsz", type=int, default=640, help="Model input size")
    p.add_argument("--recall-target", type=float, default=0.90, help="Required recall to exit 0")
    p.add_argument("--precision-target", type=float, default=0.80, help="Required precision to exit 0")
    args = p.parse_args()

    if not args.model.exists():
        print(f"❌ Model not found: {args.model}", file=sys.stderr)
        return 2

    images = sorted(list(args.images.glob("*.jpg")) + list(args.images.glob("*.JPG")) + list(args.images.glob("*.png")))
    if not images:
        print(f"❌ No images in {args.images}", file=sys.stderr)
        return 2

    print(f"Loading model: {args.model}")
    sess = ort.InferenceSession(str(args.model), providers=["CPUExecutionProvider"])
    input_name = sess.get_inputs()[0].name
    print(f"  input  {input_name}: {sess.get_inputs()[0].shape}")
    print(f"  output {sess.get_outputs()[0].name}: {sess.get_outputs()[0].shape}")
    print(f"\nEvaluating {len(images)} images @ conf={args.conf}, iou-match={args.iou_match}\n")

    total_tp, total_fp, total_fn = 0, 0, 0
    inference_times_ms: list[float] = []

    for img_path in images:
        try:
            tensor, scale, padding, orig_hw = preprocess(img_path, args.imgsz)
        except FileNotFoundError as e:
            print(f"  skip {img_path.name}: {e}")
            continue

        t0 = time.perf_counter()
        output = sess.run(None, {input_name: tensor})[0]
        elapsed_ms = (time.perf_counter() - t0) * 1000
        inference_times_ms.append(elapsed_ms)

        detections = postprocess(output, scale, padding, orig_hw, args.conf, args.iou_nms)

        if args.labels:
            label_path = args.labels / (img_path.stem + ".txt")
            gt = load_yolo_labels(label_path, orig_hw)
        else:
            gt = []  # no labels — report detection count only

        # Match detections to ground truth greedily by IoU
        matched_gt = set()
        tp_this, fp_this = 0, 0
        # Sort detections by confidence (high first) — match best first
        for det in sorted(detections, key=lambda d: -d[4]):
            best_iou, best_idx = 0.0, -1
            for i, g in enumerate(gt):
                if i in matched_gt:
                    continue
                v = iou(det[:4], g)
                if v > best_iou:
                    best_iou, best_idx = v, i
            if best_iou >= args.iou_match and best_idx >= 0:
                tp_this += 1
                matched_gt.add(best_idx)
            else:
                fp_this += 1
        fn_this = len(gt) - len(matched_gt)

        total_tp += tp_this
        total_fp += fp_this
        total_fn += fn_this

        marker = "✓" if (tp_this > 0 and fp_this == 0 and fn_this == 0) else "·"
        print(f"  {marker} {img_path.name:40s}  gt={len(gt):2d}  det={len(detections):2d}  "
              f"tp={tp_this:2d} fp={fp_this:2d} fn={fn_this:2d}  ({elapsed_ms:5.0f} ms)")

    print()
    print("=" * 60)
    print("Summary")
    print("=" * 60)

    if args.labels:
        precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else 0.0
        recall = total_tp / (total_tp + total_fn) if (total_tp + total_fn) > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        print(f"  Images:      {len(images)}")
        print(f"  Detections:  {total_tp + total_fp}")
        print(f"  Ground truth boxes: {total_tp + total_fn}")
        print(f"  True positives:  {total_tp}")
        print(f"  False positives: {total_fp}")
        print(f"  False negatives: {total_fn}")
        print(f"  Precision:   {precision:.4f}  (target ≥ {args.precision_target})")
        print(f"  Recall:      {recall:.4f}  (target ≥ {args.recall_target})")
        print(f"  F1:          {f1:.4f}")
    else:
        total_det = total_tp + total_fp  # everything is "tp" here since no gt
        print(f"  Images:      {len(images)}")
        print(f"  Detections:  {total_det}  (avg {total_det/len(images):.1f} per image)")
        print(f"  (no labels provided → no accuracy metrics)")

    print(f"  Inference time: mean={np.mean(inference_times_ms):.1f}ms  "
          f"p50={np.percentile(inference_times_ms, 50):.1f}ms  "
          f"p95={np.percentile(inference_times_ms, 95):.1f}ms  "
          f"max={np.max(inference_times_ms):.1f}ms")
    print()

    if args.labels:
        passed = (precision >= args.precision_target) and (recall >= args.recall_target)
        if passed:
            print("✅ PASS — model meets success criteria.")
            return 0
        else:
            print("❌ FAIL — model does not meet success criteria. See spec for next steps.")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
