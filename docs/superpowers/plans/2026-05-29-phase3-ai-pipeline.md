# Phase 3 — AI Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement `process_photo()` — the RQ worker that runs ONNX AI inference (bib detect → OCR → face embed → Re-ID → DB writes) for every ingested photo.

**Architecture:** Three service classes (`BibDetector`, `BibOcr`, `FaceEmbedder`) each wrap an ONNX session; `pipeline.py` orchestrates them and handles all DB writes. Sessions are preloaded once at worker startup (singleton in `tasks.py`). No `torch` or `paddle` in production (D-021).

**Tech Stack:** `onnxruntime>=1.18`, `numpy>=1.26`, `opencv-python-headless>=4.9`, `pgvector` (already installed), `sqlalchemy` async (already installed), `boto3` for R2 (already installed)

---

## ⚠️ Critical field names — read before touching models

From `apps/backend/joggy/db/models.py`:
- `Photo.bib_number_nullable` (NOT `bib_number`)
- `Photo.gender_nullable` (NOT `gender`)
- `AIReviewStatus.manual_pending` for low confidence (NOT `'pending'`)
- `AIReviewStatus.auto` for success
- `ReviewQueue.reason` values: `"no_bib"` | `"low_ocr_conf"` | `"other"`
- `FaceEmbedding.embedding` — `Vector(512)` column, store as Python list

---

## File Map

```
apps/backend/
├── joggy/
│   ├── ai/                          ← new package
│   │   ├── __init__.py
│   │   ├── session.py               Task 2 — ONNX session loader
│   │   ├── bib_detector.py          Task 3 — YOLOv8-nano wrapper
│   │   ├── bib_ocr.py               Task 4 — PaddleOCR ONNX wrapper
│   │   └── face_embedder.py         Task 5 — InsightFace buffalo_s wrapper
│   └── worker/
│       ├── pipeline.py              Task 6 — orchestrator + DB writes
│       └── tasks.py                 Task 7 — implement process_photo()
├── models/                          Task 8 — .gitkeep (populated before docker build)
│   ├── yolov8n_bib.onnx
│   ├── ocr_det.onnx
│   ├── ocr_rec.onnx
│   └── buffalo_s/
│       ├── det_10g.onnx
│       └── w600k_r50.onnx
└── tests/
    ├── ai/
    │   ├── __init__.py              Task 2
    │   ├── test_session.py          Task 2
    │   ├── test_bib_detector.py     Task 3
    │   ├── test_bib_ocr.py          Task 4
    │   └── test_face_embedder.py    Task 5
    └── worker/
        └── test_pipeline.py         Task 6 (expand existing file)

tools/
└── export/
    ├── export_yolo.py               Task 8
    └── export_ocr.py                Task 8
```

---

## Task 1: Add AI dependencies + `download_bytes()` to r2.py

**Files:**
- Modify: `apps/backend/pyproject.toml`
- Modify: `apps/backend/joggy/services/r2.py`
- Create: `apps/backend/tests/services/__init__.py`
- Create: `apps/backend/tests/services/test_r2_download.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/backend/tests/services/test_r2_download.py
import io
from unittest.mock import MagicMock, patch, ANY

from joggy.services import r2


def test_download_bytes_returns_content():
    fake_body = io.BytesIO(b"fake_jpeg_content")
    fake_client = MagicMock()
    fake_client.get_object.return_value = {"Body": fake_body}
    with patch("joggy.services.r2._get_client", return_value=fake_client):
        result = r2.download_bytes("events/abc/def/original.jpg")
    assert result == b"fake_jpeg_content"
    fake_client.get_object.assert_called_once_with(
        Bucket=ANY, Key="events/abc/def/original.jpg"
    )


def test_download_bytes_uses_correct_bucket():
    fake_body = io.BytesIO(b"data")
    fake_client = MagicMock()
    fake_client.get_object.return_value = {"Body": fake_body}
    with patch("joggy.services.r2._get_client", return_value=fake_client), \
         patch("joggy.services.r2.get_settings") as mock_settings:
        mock_settings.return_value.r2_bucket_name = "my-bucket"
        r2.download_bytes("some/key.jpg")
    fake_client.get_object.assert_called_once_with(
        Bucket="my-bucket", Key="some/key.jpg"
    )
```

- [ ] **Step 2: Create `tests/services/__init__.py`**

```
touch apps/backend/tests/services/__init__.py
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd apps/backend
uv run pytest tests/services/test_r2_download.py -v
```

Expected: `FAILED` — `AttributeError: module 'joggy.services.r2' has no attribute 'download_bytes'`

- [ ] **Step 4: Add `download_bytes()` to r2.py**

Add after `upload_bytes()` in `apps/backend/joggy/services/r2.py`:

```python
def download_bytes(key: str) -> bytes:
    """ดาวน์โหลด object จาก R2 เป็น bytes — ใช้โดย AI pipeline worker."""
    response = _get_client().get_object(
        Bucket=get_settings().r2_bucket_name,
        Key=key,
    )
    return response["Body"].read()
```

- [ ] **Step 5: Add AI dependencies to `apps/backend/pyproject.toml`**

In the `dependencies` list, add these three lines after `"boto3>=1.38"`:

```toml
  "onnxruntime>=1.18.0,<2.0.0",
  "numpy>=1.26.0,<3.0.0",
  "opencv-python-headless>=4.9.0,<5.0.0",
```

- [ ] **Step 6: Sync dependencies**

```bash
cd apps/backend
uv sync
```

Expected: installs `onnxruntime`, `numpy`, `opencv-python-headless`

- [ ] **Step 7: Run tests to verify they pass**

```bash
uv run pytest tests/services/test_r2_download.py -v
```

Expected: `2 passed`

- [ ] **Step 8: Commit**

```bash
git add apps/backend/pyproject.toml apps/backend/joggy/services/r2.py \
        apps/backend/tests/services/__init__.py \
        apps/backend/tests/services/test_r2_download.py \
        uv.lock
git commit -m "feat(ai): add onnxruntime/numpy/opencv deps + r2.download_bytes()"
```

---

## Task 2: Create `joggy/ai/` package + `session.py`

**Files:**
- Create: `apps/backend/joggy/ai/__init__.py`
- Create: `apps/backend/joggy/ai/session.py`
- Create: `apps/backend/tests/ai/__init__.py`
- Create: `apps/backend/tests/ai/test_session.py`

- [ ] **Step 1: Write the failing test**

```python
# apps/backend/tests/ai/test_session.py
from unittest.mock import MagicMock, patch, call
import pytest

from joggy.ai.session import ModelSessions, load_sessions


def test_load_sessions_creates_five_sessions():
    with patch("joggy.ai.session.ort.InferenceSession") as mock_cls:
        mock_cls.return_value = MagicMock()
        sessions = load_sessions("fake_models")
    assert mock_cls.call_count == 5
    assert isinstance(sessions, ModelSessions)


def test_load_sessions_uses_correct_paths():
    with patch("joggy.ai.session.ort.InferenceSession") as mock_cls:
        mock_cls.return_value = MagicMock()
        load_sessions("/models")
    paths = [c.args[0] for c in mock_cls.call_args_list]
    assert "/models/yolov8n_bib.onnx" in paths
    assert "/models/ocr_det.onnx" in paths
    assert "/models/ocr_rec.onnx" in paths
    assert "/models/buffalo_s/det_10g.onnx" in paths
    assert "/models/buffalo_s/w600k_r50.onnx" in paths


def test_load_sessions_uses_cpu_provider():
    with patch("joggy.ai.session.ort.InferenceSession") as mock_cls:
        mock_cls.return_value = MagicMock()
        load_sessions("/models")
    for c in mock_cls.call_args_list:
        assert c.kwargs.get("providers") == ["CPUExecutionProvider"]
```

- [ ] **Step 2: Create package files**

`apps/backend/joggy/ai/__init__.py` — empty file

`apps/backend/tests/ai/__init__.py` — empty file

- [ ] **Step 3: Run test to verify it fails**

```bash
cd apps/backend
uv run pytest tests/ai/test_session.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'joggy.ai'`

- [ ] **Step 4: Write `apps/backend/joggy/ai/session.py`**

```python
"""
ONNX session loader — preload all AI models at worker startup.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY — ห้าม import torch / paddle ในไฟล์นี้
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import onnxruntime as ort


@dataclass
class ModelSessions:
    """ONNX InferenceSession สำหรับ 5 model — ส่งผ่าน constructor ไม่ใช่ global."""
    yolo: ort.InferenceSession
    ocr_det: ort.InferenceSession
    ocr_rec: ort.InferenceSession
    face_det: ort.InferenceSession
    face_embed: ort.InferenceSession


def load_sessions(model_dir: str = "models") -> ModelSessions:
    """
    โหลด ONNX sessions ทั้งหมดตอน worker boot.
    เรียกครั้งเดียว — เก็บเป็น module-level singleton ใน tasks.py
    """
    def _load(path: str) -> ort.InferenceSession:
        full = os.path.join(model_dir, path)
        return ort.InferenceSession(full, providers=["CPUExecutionProvider"])

    return ModelSessions(
        yolo=_load("yolov8n_bib.onnx"),
        ocr_det=_load("ocr_det.onnx"),
        ocr_rec=_load("ocr_rec.onnx"),
        face_det=_load("buffalo_s/det_10g.onnx"),
        face_embed=_load("buffalo_s/w600k_r50.onnx"),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/ai/test_session.py -v
```

Expected: `3 passed`

- [ ] **Step 6: Commit**

```bash
git add apps/backend/joggy/ai/ apps/backend/tests/ai/
git commit -m "feat(ai): add joggy/ai package + session.py ONNX loader"
```

---

## Task 3: `bib_detector.py` — YOLOv8-nano ONNX

**Files:**
- Create: `apps/backend/joggy/ai/bib_detector.py`
- Create: `apps/backend/tests/ai/test_bib_detector.py`

> **Model note:** YOLOv8-nano custom 1-class (bib) ONNX output shape: `(1, 5, 8400)` — [cx, cy, w, h, conf] in model input space (640×640). Input tensor name: `"images"`. If your export differs, check with `session.get_inputs()[0].name` and `session.get_outputs()[0].name`.

- [ ] **Step 1: Write the failing tests**

```python
# apps/backend/tests/ai/test_bib_detector.py
import numpy as np
import pytest
from unittest.mock import MagicMock

from joggy.ai.bib_detector import BibBox, BibDetector

_INPUT_SIZE = 640


def _make_img(h: int = 480, w: int = 640) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_session(output: np.ndarray) -> MagicMock:
    sess = MagicMock()
    sess.run.return_value = [output]
    return sess


def test_detect_returns_bib_box_when_confident():
    # cx=320, cy=200, bw=100, bh=50 in 640-space; conf=0.9
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    output[0, 0, 0] = 320.0   # cx
    output[0, 1, 0] = 200.0   # cy
    output[0, 2, 0] = 100.0   # bw
    output[0, 3, 0] = 50.0    # bh
    output[0, 4, 0] = 0.9     # conf
    result = BibDetector(_make_session(output)).detect(_make_img())
    assert isinstance(result, BibBox)
    assert result.confidence == pytest.approx(0.9)


def test_detect_returns_none_when_all_conf_zero():
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    assert BibDetector(_make_session(output)).detect(_make_img()) is None


def test_detect_returns_none_below_threshold():
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    output[0, 4, 0] = 0.3   # below _CONF_THRESHOLD (0.5)
    assert BibDetector(_make_session(output)).detect(_make_img()) is None


def test_detect_uses_images_input_key():
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    sess = _make_session(output)
    BibDetector(sess).detect(_make_img())
    input_dict = sess.run.call_args[0][1]
    assert "images" in input_dict


def test_detect_bbox_coordinates_scale_to_original():
    # 640×640 model space → 640×480 original: sy = 480/640 = 0.75
    # cx=320, cy=200, bw=100, bh=50 → x1=(320-50)/1.0=270, y1=(200-25)/0.75≈233
    output = np.zeros((1, 5, 8400), dtype=np.float32)
    output[0, 0, 0] = 320.0
    output[0, 1, 0] = 200.0
    output[0, 2, 0] = 100.0
    output[0, 3, 0] = 50.0
    output[0, 4, 0] = 0.9
    result = BibDetector(_make_session(output)).detect(_make_img(h=480, w=640))
    assert result is not None
    assert result.x1 == 270  # (320-50)/1.0
    assert result.x2 == 370  # (320+50)/1.0
```

- [ ] **Step 2: Run to verify failures**

```bash
cd apps/backend
uv run pytest tests/ai/test_bib_detector.py -v
```

Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 3: Write `apps/backend/joggy/ai/bib_detector.py`**

```python
"""
BibDetector — YOLOv8-nano ONNX bib detection.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY
Model output format: (1, 5, 8400) — [cx, cy, w, h, conf] per anchor
Input tensor name: "images" (verify with session.get_inputs()[0].name)
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

_INPUT_SIZE = 640
_CONF_THRESHOLD = 0.5


@dataclass
class BibBox:
    """Bib bounding box ในพิกัดรูปต้นฉบับ."""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class BibDetector:
    """YOLOv8-nano wrapper สำหรับตรวจ bib number region."""

    def __init__(self, session: ort.InferenceSession) -> None:
        self._sess = session

    def detect(self, img_bgr: np.ndarray) -> BibBox | None:
        """
        ตรวจหา bib ในรูป BGR.
        Returns: BibBox ที่ confidence สูงสุด หรือ None ถ้าไม่เจอ.
        """
        tensor, sx, sy = self._preprocess(img_bgr)
        outputs = self._sess.run(None, {"images": tensor})
        return self._postprocess(outputs[0], sx, sy)

    # ── private ──────────────────────────────────────────────────────────────

    def _preprocess(self, img_bgr: np.ndarray) -> tuple[np.ndarray, float, float]:
        """Resize to 640×640, normalize [0,1], return NCHW float32 + scale factors."""
        h, w = img_bgr.shape[:2]
        sx = _INPUT_SIZE / w
        sy = _INPUT_SIZE / h
        resized = cv2.resize(img_bgr, (_INPUT_SIZE, _INPUT_SIZE))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        tensor = rgb.transpose(2, 0, 1)[np.newaxis].astype(np.float32) / 255.0
        return tensor, sx, sy

    def _postprocess(
        self, output: np.ndarray, sx: float, sy: float
    ) -> BibBox | None:
        """
        Parse YOLOv8 output (1, 5, 8400).
        Each anchor: [cx, cy, w, h, conf] in model input coordinate space.
        """
        preds = output[0].T          # (8400, 5)
        confs = preds[:, 4]
        mask = confs > _CONF_THRESHOLD
        if not mask.any():
            return None
        filtered_confs = confs[mask]
        best_idx = int(filtered_confs.argmax())
        best = preds[mask][best_idx]
        cx, cy, bw, bh = best[:4]
        conf = float(filtered_confs[best_idx])
        x1 = max(0, int((cx - bw / 2) / sx))
        y1 = max(0, int((cy - bh / 2) / sy))
        x2 = int((cx + bw / 2) / sx)
        y2 = int((cy + bh / 2) / sy)
        return BibBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/ai/test_bib_detector.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/backend/joggy/ai/bib_detector.py apps/backend/tests/ai/test_bib_detector.py
git commit -m "feat(ai): BibDetector — YOLOv8-nano ONNX bib detection"
```

---

## Task 4: `bib_ocr.py` — PaddleOCR ONNX

**Files:**
- Create: `apps/backend/joggy/ai/bib_ocr.py`
- Create: `apps/backend/tests/ai/test_bib_ocr.py`

> **Model note:** PP-OCRv4 recognition model. Input tensor name: `"x"`, output tensor name: `"softmax_0.tmp_0"`. Shape: input `(1, 3, 48, W)` variable-width, output `(1, T, 11)` for digits 0–9 + blank. Verify with `session.get_inputs()[0].name`. Detection session (`ocr_det`) is loaded but the pipeline only uses `rec` for bib region (bounding box already known from YOLOv8).

- [ ] **Step 1: Write the failing tests**

```python
# apps/backend/tests/ai/test_bib_ocr.py
import numpy as np
import pytest
from unittest.mock import MagicMock

from joggy.ai.bib_detector import BibBox
from joggy.ai.bib_ocr import BibOcr, BibResult, _BLANK


def _make_img(h: int = 100, w: int = 200) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_bbox(x1=0, y1=0, x2=100, y2=50) -> BibBox:
    return BibBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=0.9)


def _rec_session(logits: np.ndarray) -> MagicMock:
    sess = MagicMock()
    sess.run.return_value = [logits]
    return sess


def test_read_returns_none_when_bbox_none():
    ocr = BibOcr(MagicMock(), MagicMock())
    assert ocr.read(_make_img(), None) is None


def test_read_returns_bib_result_for_digit_sequence():
    # "1234" — T=4, C=11 (10 digits + blank=10)
    T, C = 4, 11
    logits = np.full((1, T, C), 0.01, dtype=np.float32)
    for t, idx in enumerate([1, 2, 3, 4]):
        logits[0, t, :] = 0.01
        logits[0, t, idx] = 0.95
    result = BibOcr(MagicMock(), _rec_session(logits)).read(_make_img(), _make_bbox())
    assert result is not None
    assert result.number == "1234"
    assert result.confidence > 0.9


def test_read_returns_none_when_all_blank():
    T, C = 5, 11
    logits = np.zeros((1, T, C), dtype=np.float32)
    logits[0, :, _BLANK] = 0.99   # all blanks
    assert BibOcr(MagicMock(), _rec_session(logits)).read(_make_img(), _make_bbox()) is None


def test_read_uses_x_input_key():
    T, C = 2, 11
    logits = np.zeros((1, T, C), dtype=np.float32)
    logits[0, 0, 1] = 0.95   # "1"
    rec_sess = _rec_session(logits)
    BibOcr(MagicMock(), rec_sess).read(_make_img(), _make_bbox())
    input_dict = rec_sess.run.call_args[0][1]
    assert "x" in input_dict


def test_read_confidence_is_mean_of_char_probs():
    T, C = 2, 11
    logits = np.zeros((1, T, C), dtype=np.float32)
    logits[0, 0, 1] = 0.8    # "1" at 0.8
    logits[0, 1, 2] = 0.6    # "2" at 0.6
    result = BibOcr(MagicMock(), _rec_session(logits)).read(_make_img(), _make_bbox())
    assert result is not None
    assert result.confidence == pytest.approx(0.7, abs=0.01)
```

- [ ] **Step 2: Run to verify failures**

```bash
uv run pytest tests/ai/test_bib_ocr.py -v
```

Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 3: Write `apps/backend/joggy/ai/bib_ocr.py`**

```python
"""
BibOcr — PaddleOCR ONNX recognition for bib numbers (digits only).
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY
Recognition model input: "x" tensor (1, 3, 48, W) float32
Recognition model output: "softmax_0.tmp_0" (1, T, 11) — 10 digits + blank
Verify tensor names: session.get_inputs()[0].name, session.get_outputs()[0].name
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import cv2
import numpy as np
import onnxruntime as ort

if TYPE_CHECKING:
    from joggy.ai.bib_detector import BibBox

_REC_HEIGHT = 48
_CHARS = "0123456789"
_BLANK = len(_CHARS)   # index 10 = CTC blank token


@dataclass
class BibResult:
    number: str         # e.g. "1234"
    confidence: float   # mean per-character softmax probability, 0.0–1.0


class BibOcr:
    """PaddleOCR ONNX wrapper — อ่านเลขบิบจาก cropped region."""

    def __init__(
        self,
        det_sess: ort.InferenceSession,
        rec_sess: ort.InferenceSession,
    ) -> None:
        self._det = det_sess   # loaded but unused (bbox already known from YOLO)
        self._rec = rec_sess

    def read(self, img_bgr: np.ndarray, bbox: "BibBox | None") -> BibResult | None:
        """
        Crop bib region → อ่านเลข → BibResult | None.
        bbox=None → return None immediately.
        """
        if bbox is None:
            return None
        crop = img_bgr[bbox.y1:bbox.y2, bbox.x1:bbox.x2]
        if crop.size == 0:
            return None
        tensor = self._preprocess(crop)
        outputs = self._rec.run(None, {"x": tensor})
        return self._ctc_decode(outputs[0])

    # ── private ──────────────────────────────────────────────────────────────

    def _preprocess(self, crop_bgr: np.ndarray) -> np.ndarray:
        """Resize crop to height=48, normalize to [-1,1], NCHW float32."""
        h, w = crop_bgr.shape[:2]
        new_w = max(1, int(w * _REC_HEIGHT / h))
        resized = cv2.resize(crop_bgr, (new_w, _REC_HEIGHT))
        rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32)
        normalized = (rgb / 127.5) - 1.0   # range [-1, 1]
        return normalized.transpose(2, 0, 1)[np.newaxis]  # (1, 3, 48, W)

    def _ctc_decode(self, logits: np.ndarray) -> BibResult | None:
        """
        CTC greedy decode — logits shape (1, T, 11).
        Remove blanks + consecutive duplicates, then assemble digit string.
        """
        probs = logits[0]          # (T, 11)
        indices = probs.argmax(axis=1)   # (T,)
        chars: list[str] = []
        confs: list[float] = []
        prev = _BLANK
        for t, idx in enumerate(indices):
            if idx != _BLANK and idx != prev:
                chars.append(_CHARS[idx])
                confs.append(float(probs[t, idx]))
            prev = int(idx)
        if not chars:
            return None
        number = "".join(chars)
        if not number.isdigit():
            return None
        return BibResult(number=number, confidence=float(np.mean(confs)))
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/ai/test_bib_ocr.py -v
```

Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/backend/joggy/ai/bib_ocr.py apps/backend/tests/ai/test_bib_ocr.py
git commit -m "feat(ai): BibOcr — PaddleOCR ONNX bib number recognition"
```

---

## Task 5: `face_embedder.py` — InsightFace buffalo_s ONNX

**Files:**
- Create: `apps/backend/joggy/ai/face_embedder.py`
- Create: `apps/backend/tests/ai/test_face_embedder.py`

> **Model note:** `det_10g.onnx` input: `"input.1"` shape `(1, 3, 640, 640)`. Outputs: 9 tensors (3 strides × [scores, bboxes, landmarks]). `w600k_r50.onnx` input: `"input.1"` shape `(1, 3, 112, 112)`, output: `"683"` shape `(1, 512)`. Verify names with `session.get_inputs()[0].name`.

- [ ] **Step 1: Write the failing tests**

```python
# apps/backend/tests/ai/test_face_embedder.py
import numpy as np
import pytest
from unittest.mock import MagicMock

from joggy.ai.face_embedder import FaceEmbedder, FaceResult


def _make_img(h: int = 480, w: int = 640) -> np.ndarray:
    return np.zeros((h, w, 3), dtype=np.uint8)


def _make_no_face_det_output():
    """9 output tensors all zeros — no face detected."""
    return [np.zeros((1, 1, 1), dtype=np.float32)] * 9


def _make_face_det_output():
    """
    Minimal det output: 1 face at stride 8 with conf=0.9.
    outputs[0]=scores_8, outputs[3]=bboxes_8, outputs[6]=landmarks_8
    """
    outputs = [np.zeros((1, 1, 1), dtype=np.float32)] * 9
    outputs[0] = np.array([[[0.9]]], dtype=np.float32)   # scores stride 8
    outputs[3] = np.array([[100.0, 100.0, 200.0, 200.0]], dtype=np.float32).reshape(1, 1, 4)
    lm = np.array([[[130, 140], [170, 140], [150, 160], [135, 180], [165, 180]]], dtype=np.float32)
    outputs[6] = lm
    return outputs


def test_embed_returns_none_when_no_face():
    det_sess = MagicMock()
    det_sess.run.return_value = _make_no_face_det_output()
    embed_sess = MagicMock()
    result = FaceEmbedder(det_sess, embed_sess).embed(_make_img())
    assert result is None
    embed_sess.run.assert_not_called()


def test_embed_returns_face_result_when_face_detected():
    det_sess = MagicMock()
    det_sess.run.return_value = _make_face_det_output()
    fake_vec = np.random.randn(1, 512).astype(np.float32)
    embed_sess = MagicMock()
    embed_sess.run.return_value = [fake_vec]
    result = FaceEmbedder(det_sess, embed_sess).embed(_make_img())
    assert isinstance(result, FaceResult)
    assert result.vector.shape == (512,)


def test_embed_vector_is_l2_normalised():
    det_sess = MagicMock()
    det_sess.run.return_value = _make_face_det_output()
    raw_vec = np.ones((1, 512), dtype=np.float32) * 2.0
    embed_sess = MagicMock()
    embed_sess.run.return_value = [raw_vec]
    result = FaceEmbedder(det_sess, embed_sess).embed(_make_img())
    assert result is not None
    norm = float(np.linalg.norm(result.vector))
    assert norm == pytest.approx(1.0, abs=1e-5)


def test_embed_does_not_call_embed_when_no_face():
    det_sess = MagicMock()
    det_sess.run.return_value = _make_no_face_det_output()
    embed_sess = MagicMock()
    FaceEmbedder(det_sess, embed_sess).embed(_make_img())
    embed_sess.run.assert_not_called()
```

- [ ] **Step 2: Run to verify failures**

```bash
uv run pytest tests/ai/test_face_embedder.py -v
```

Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 3: Write `apps/backend/joggy/ai/face_embedder.py`**

```python
"""
FaceEmbedder — InsightFace buffalo_s ONNX det + embed.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY
⚠️  SECURITY: face embedding = biometric data (D-014) — ห้าม return ผ่าน API

det_10g.onnx:   input "input.1" (1,3,640,640); outputs 9 tensors (stride 8/16/32)
w600k_r50.onnx: input "input.1" (1,3,112,112); output "683" (1,512)
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import onnxruntime as ort

_DET_SIZE = 640
_EMBED_SIZE = 112
_DET_CONF = 0.5

# ArcFace 5-point alignment template (from InsightFace repo)
_ARCFACE_DST = np.array([
    [38.2946, 51.6963],
    [73.5318, 51.5014],
    [56.0252, 71.7366],
    [41.5493, 92.3655],
    [70.7299, 92.2041],
], dtype=np.float32)


@dataclass
class FaceBox:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    landmarks: np.ndarray  # (5, 2)


@dataclass
class FaceResult:
    """512-dim L2-normalised face embedding — ⚠️ biometric data."""
    vector: np.ndarray   # shape (512,) float32 L2-normalised
    box: FaceBox


class FaceEmbedder:
    """InsightFace buffalo_s det + embed wrapper."""

    def __init__(
        self,
        det_sess: ort.InferenceSession,
        embed_sess: ort.InferenceSession,
    ) -> None:
        self._det = det_sess
        self._embed = embed_sess

    def embed(self, img_bgr: np.ndarray) -> FaceResult | None:
        """ตรวจหน้า → align → embed → return FaceResult | None."""
        h, w = img_bgr.shape[:2]
        tensor, scale = self._det_preprocess(img_bgr)
        det_outputs = self._det.run(None, {"input.1": tensor})
        face_box = self._parse_detections(det_outputs, scale)
        if face_box is None:
            return None
        aligned = self._align_face(img_bgr, face_box.landmarks)
        embed_tensor = self._embed_preprocess(aligned)
        raw = self._embed.run(None, {"input.1": embed_tensor})[0]
        vector = self._l2_normalize(raw[0])
        return FaceResult(vector=vector, box=face_box)

    # ── private ──────────────────────────────────────────────────────────────

    def _det_preprocess(self, img_bgr: np.ndarray) -> tuple[np.ndarray, float]:
        h, w = img_bgr.shape[:2]
        scale = _DET_SIZE / max(h, w)
        new_h, new_w = int(h * scale), int(w * scale)
        resized = cv2.resize(img_bgr, (new_w, new_h)).astype(np.float32)
        canvas = np.zeros((_DET_SIZE, _DET_SIZE, 3), dtype=np.float32)
        canvas[:new_h, :new_w] = resized
        return canvas.transpose(2, 0, 1)[np.newaxis], scale

    def _parse_detections(
        self, outputs: list[np.ndarray], scale: float
    ) -> FaceBox | None:
        """
        det_10g outputs[0..2] = scores per stride (8/16/32)
        outputs[3..5] = bboxes, outputs[6..8] = landmarks
        Pick highest-confidence face above _DET_CONF threshold.
        """
        all_scores, all_bboxes, all_lm = [], [], []
        for i in range(3):
            scores = outputs[i].reshape(-1)
            bboxes = outputs[3 + i].reshape(-1, 4)
            lmarks = outputs[6 + i].reshape(-1, 5, 2)
            mask = scores > _DET_CONF
            if mask.any():
                all_scores.append(scores[mask])
                all_bboxes.append(bboxes[mask] / scale)
                all_lm.append(lmarks[mask] / scale)
        if not all_scores:
            return None
        sc = np.concatenate(all_scores)
        bx = np.concatenate(all_bboxes)
        lm = np.concatenate(all_lm)
        best = int(sc.argmax())
        x1, y1, x2, y2 = bx[best]
        return FaceBox(
            x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2),
            confidence=float(sc[best]),
            landmarks=lm[best].astype(np.float32),
        )

    def _align_face(self, img_bgr: np.ndarray, landmarks: np.ndarray) -> np.ndarray:
        """Affine-align face to 112×112 using 5-point landmarks."""
        M, _ = cv2.estimateAffinePartial2D(landmarks, _ARCFACE_DST, method=cv2.RANSAC)
        if M is None:
            h, w = img_bgr.shape[:2]
            s = min(h, w)
            crop = img_bgr[(h - s) // 2:(h + s) // 2, (w - s) // 2:(w + s) // 2]
            return cv2.resize(crop, (_EMBED_SIZE, _EMBED_SIZE))
        return cv2.warpAffine(img_bgr, M, (_EMBED_SIZE, _EMBED_SIZE))

    def _embed_preprocess(self, face_bgr: np.ndarray) -> np.ndarray:
        """Normalize to [-1,1], NCHW float32."""
        arr = face_bgr.astype(np.float32)
        normalized = (arr / 127.5) - 1.0
        return normalized.transpose(2, 0, 1)[np.newaxis]

    @staticmethod
    def _l2_normalize(vec: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vec))
        if norm < 1e-6:
            return vec
        return (vec / norm).astype(np.float32)
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/ai/test_face_embedder.py -v
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/backend/joggy/ai/face_embedder.py apps/backend/tests/ai/test_face_embedder.py
git commit -m "feat(ai): FaceEmbedder — InsightFace buffalo_s ONNX det+embed"
```

---

## Task 6: `pipeline.py` — Orchestrator + DB writes + Re-ID

**Files:**
- Create: `apps/backend/joggy/worker/pipeline.py`
- Expand: `apps/backend/tests/worker/test_pipeline.py`

- [ ] **Step 1: Write the failing tests**

```python
# apps/backend/tests/worker/test_pipeline.py
# (add these tests to the existing file, or replace if file only has queue tests)
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np
import pytest

from joggy.ai.bib_detector import BibBox
from joggy.ai.bib_ocr import BibResult
from joggy.ai.face_embedder import FaceResult, FaceBox
from joggy.db.models import AIReviewStatus, Photo, Event, ReviewQueueStatus
from joggy.worker.pipeline import run_pipeline, _BIB_CONF_THRESHOLD


def _make_photo(event_id: uuid.UUID) -> Photo:
    return Photo(
        id=uuid.uuid4(),
        event_id=event_id,
        uploaded_by_event_token_id=uuid.uuid4(),
        device_id="pi-001",
        r2_key_original="events/e/p/original.jpg",
        sha256="abc123",
    )


def _make_event() -> Event:
    now = datetime.now(timezone.utc)
    return Event(
        id=uuid.uuid4(),
        organizer_id=uuid.uuid4(),
        name="Test Race",
        start_at=now - timedelta(hours=5),
        end_at=now + timedelta(hours=1),
    )


def _make_face_result() -> FaceResult:
    vec = np.ones(512, dtype=np.float32)
    vec /= np.linalg.norm(vec)
    box = FaceBox(x1=10.0, y1=10.0, x2=80.0, y2=90.0, confidence=0.95,
                  landmarks=np.zeros((5, 2), dtype=np.float32))
    return FaceResult(vector=vec, box=box)


def _make_sessions():
    sessions = MagicMock()
    return sessions


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def event():
    return _make_event()


@pytest.fixture
def photo(event):
    return _make_photo(event.id)


def _setup_db_queries(mock_db, photo, event, reid_rows=None):
    """Mock db.execute to return photo, then event, then optional reid rows."""
    photo_result = MagicMock()
    photo_result.scalar_one_or_none.return_value = photo
    event_result = MagicMock()
    event_result.scalar_one_or_none.return_value = event
    reid_result = MagicMock()
    reid_result.fetchall.return_value = reid_rows or []
    mock_db.execute.side_effect = [photo_result, event_result, reid_result]


@pytest.mark.asyncio
async def test_happy_path_auto_status(mock_db, photo, event):
    _setup_db_queries(mock_db, photo, event)
    sessions = _make_sessions()
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        bbox = BibBox(0, 0, 50, 30, 0.9)
        MockDet.return_value.detect.return_value = bbox
        MockOcr.return_value.read.return_value = BibResult(number="1234", confidence=0.92)
        MockEmbed.return_value.embed.return_value = _make_face_result()

        result = await run_pipeline(str(photo.id), mock_db, sessions)

    assert result["bib_number"] == "1234"
    assert result["ai_review_status"] == AIReviewStatus.auto.value
    assert result["needs_review"] is False


@pytest.mark.asyncio
async def test_low_confidence_triggers_review_queue(mock_db, photo, event):
    _setup_db_queries(mock_db, photo, event)
    sessions = _make_sessions()
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        bbox = BibBox(0, 0, 50, 30, 0.9)
        MockDet.return_value.detect.return_value = bbox
        # confidence below threshold
        MockOcr.return_value.read.return_value = BibResult(number="1234", confidence=0.50)
        MockEmbed.return_value.embed.return_value = None

        result = await run_pipeline(str(photo.id), mock_db, sessions)

    assert result["ai_review_status"] == AIReviewStatus.manual_pending.value
    assert result["needs_review"] is True
    # verify ReviewQueue was added
    added_types = [type(call.args[0]).__name__ for call in mock_db.add.call_args_list]
    assert "ReviewQueue" in added_types


@pytest.mark.asyncio
async def test_no_bib_triggers_review_queue(mock_db, photo, event):
    _setup_db_queries(mock_db, photo, event)
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        MockDet.return_value.detect.return_value = None
        MockOcr.return_value.read.return_value = None
        MockEmbed.return_value.embed.return_value = None

        result = await run_pipeline(str(photo.id), mock_db, _make_sessions())

    assert result["bib_number"] is None
    assert result["needs_review"] is True


@pytest.mark.asyncio
async def test_reid_match_resolves_bib(mock_db, photo, event):
    # Re-ID returns a match row: bib="5678", similarity=0.91
    reid_rows = [("5678", 0.91)]
    _setup_db_queries(mock_db, photo, event, reid_rows=reid_rows)
    fake_img = np.zeros((100, 100, 3), dtype=np.uint8)

    with patch("joggy.worker.pipeline.r2.download_bytes", return_value=b"jpg"), \
         patch("joggy.worker.pipeline.cv2.imdecode", return_value=fake_img), \
         patch("joggy.worker.pipeline.BibDetector") as MockDet, \
         patch("joggy.worker.pipeline.BibOcr") as MockOcr, \
         patch("joggy.worker.pipeline.FaceEmbedder") as MockEmbed:

        MockDet.return_value.detect.return_value = None
        MockOcr.return_value.read.return_value = None
        MockEmbed.return_value.embed.return_value = _make_face_result()

        result = await run_pipeline(str(photo.id), mock_db, _make_sessions())

    assert result["bib_number"] == "5678"
    assert result["reid_match"] == "5678"
    assert result["needs_review"] is False
```

- [ ] **Step 2: Run to verify failures**

```bash
uv run pytest tests/worker/test_pipeline.py -v -k "test_happy_path or test_low_conf or test_no_bib or test_reid"
```

Expected: `FAILED` — `ImportError: cannot import name 'run_pipeline'`

- [ ] **Step 3: Write `apps/backend/joggy/worker/pipeline.py`**

```python
"""
AI processing pipeline — orchestrates AI services + DB writes for 1 photo.
Claude (Tech Lead) — Phase 3

⚠️  D-021: onnxruntime ONLY — ห้าม import torch / paddle
⚠️  SECURITY: face embedding ห้าม return ผ่าน API (D-014, AGENTS.md)

Flow:
  1. Load Photo + Event from DB
  2. Download JPEG from R2
  3. BibDetector → BibOcr (bib_number, confidence)
  4. FaceEmbedder (512-dim vector)
  5. UPDATE photos
  6. INSERT face_embeddings (if face found)
  7. Cross-checkpoint Re-ID (if no bib + has face)
  8. INSERT review_queue if needed
  9. AuditLog
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import cv2
import numpy as np
from sqlalchemy import select, text

from joggy.ai.bib_detector import BibDetector
from joggy.ai.bib_ocr import BibOcr
from joggy.ai.face_embedder import FaceEmbedder
from joggy.db.models import (
    ActorKind,
    AIReviewStatus,
    AuditLog,
    Event,
    FaceEmbedding,
    Photo,
    ReviewQueue,
    ReviewQueueStatus,
)
from joggy.services import r2

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from joggy.ai.session import ModelSessions

logger = logging.getLogger(__name__)

_BIB_CONF_THRESHOLD = 0.70
_REID_SIM_THRESHOLD = 0.85


async def run_pipeline(
    photo_id: str,
    db: AsyncSession,
    sessions: ModelSessions,
) -> dict:
    """
    Main pipeline — called from tasks._process_photo_async().
    Returns summary dict. Raises on unrecoverable errors (triggers RQ retry).
    """
    detector = BibDetector(sessions.yolo)
    ocr = BibOcr(sessions.ocr_det, sessions.ocr_rec)
    embedder = FaceEmbedder(sessions.face_det, sessions.face_embed)

    photo_uuid = uuid.UUID(photo_id)

    # 1. Load Photo + Event
    photo: Photo | None = (await db.execute(
        select(Photo).where(Photo.id == photo_uuid)
    )).scalar_one_or_none()
    if photo is None:
        raise ValueError(f"Photo not found: {photo_id}")

    event: Event | None = (await db.execute(
        select(Event).where(Event.id == photo.event_id)
    )).scalar_one_or_none()
    if event is None:
        raise ValueError(f"Event not found: {photo.event_id}")

    # 2. Download + decode JPEG
    img_bytes = r2.download_bytes(photo.r2_key_original)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img_bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img_bgr is None:
        raise ValueError(f"Cannot decode image for photo {photo_id}")

    # 3. Bib detection + OCR
    bbox = detector.detect(img_bgr)
    bib_result = ocr.read(img_bgr, bbox) if bbox is not None else None

    # 4. Face embedding
    face_result = embedder.embed(img_bgr)

    # 5. Determine status
    bib_ok = bib_result is not None and bib_result.confidence >= _BIB_CONF_THRESHOLD
    ai_status = AIReviewStatus.auto if bib_ok else AIReviewStatus.manual_pending

    # 5b. UPDATE Photo
    photo.bib_number_nullable = bib_result.number if bib_result is not None else None
    photo.bib_confidence = bib_result.confidence if bib_result is not None else 0.0
    photo.ai_review_status = ai_status
    db.add(photo)

    # 6. INSERT FaceEmbedding
    face_embedding_id: str | None = None
    if face_result is not None:
        retention_until = event.end_at.replace(tzinfo=timezone.utc) + timedelta(days=7)
        fe = FaceEmbedding(
            photo_id=photo_uuid,
            embedding=face_result.vector.tolist(),
            face_box_x=face_result.box.x1,
            face_box_y=face_result.box.y1,
            face_box_w=face_result.box.x2 - face_result.box.x1,
            face_box_h=face_result.box.y2 - face_result.box.y1,
            detection_confidence=face_result.box.confidence,
            retention_until=retention_until,
        )
        db.add(fe)
        await db.flush()
        face_embedding_id = str(fe.id)

    # 7. Cross-checkpoint Re-ID (no bib yet + face available)
    reid_matched_bib: str | None = None
    if photo.bib_number_nullable is None and face_result is not None:
        reid_matched_bib = await _reid_query(db, photo.event_id, face_result.vector)
        if reid_matched_bib is not None:
            photo.bib_number_nullable = reid_matched_bib
            photo.ai_review_status = AIReviewStatus.auto
            db.add(photo)

    # 8. INSERT review_queue if still unresolved
    needs_review = (
        photo.bib_number_nullable is None
        or photo.ai_review_status == AIReviewStatus.manual_pending
    )
    if needs_review:
        reason = "no_bib" if photo.bib_number_nullable is None else "low_ocr_conf"
        db.add(ReviewQueue(
            photo_id=photo_uuid,
            reason=reason,
            status=ReviewQueueStatus.pending,
        ))

    # 9. AuditLog
    db.add(AuditLog(
        actor_kind=ActorKind.system,
        action="ai_pipeline_complete",
        target_kind="photo",
        target_id=photo_uuid,
        context={
            "bib_number": photo.bib_number_nullable,
            "bib_confidence": photo.bib_confidence,
            "ai_status": photo.ai_review_status.value,
            "reid_match": reid_matched_bib,
            "face_embedding_id": face_embedding_id,
        },
    ))

    await db.commit()
    return {
        "photo_id": photo_id,
        "bib_number": photo.bib_number_nullable,
        "bib_confidence": photo.bib_confidence,
        "ai_review_status": photo.ai_review_status.value,
        "reid_match": reid_matched_bib,
        "needs_review": needs_review,
    }


async def _reid_query(
    db: AsyncSession,
    event_id: uuid.UUID,
    query_vector: np.ndarray,
) -> str | None:
    """
    pgvector cosine similarity search — same event only (D-021).
    Returns: bib_number หรือ None ถ้าไม่มี match เกิน threshold.
    """
    vec_str = "[" + ",".join(f"{v:.6f}" for v in query_vector.tolist()) + "]"
    rows = (await db.execute(
        text("""
            SELECT p.bib_number_nullable,
                   1 - (fe.embedding <=> CAST(:vec AS vector)) AS similarity
            FROM face_embeddings fe
            JOIN photos p ON p.id = fe.photo_id
            WHERE p.event_id = :event_id
              AND p.bib_number_nullable IS NOT NULL
            ORDER BY similarity DESC
            LIMIT 5
        """),
        {"vec": vec_str, "event_id": str(event_id)},
    )).fetchall()

    for bib_number, similarity in rows:
        if float(similarity) >= _REID_SIM_THRESHOLD:
            return str(bib_number)
    return None
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/worker/test_pipeline.py -v -k "test_happy_path or test_low_conf or test_no_bib or test_reid"
```

Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add apps/backend/joggy/worker/pipeline.py apps/backend/tests/worker/test_pipeline.py
git commit -m "feat(ai): pipeline.py — orchestrator + DB writes + Re-ID"
```

---

## Task 7: Implement `process_photo()` in `tasks.py`

**Files:**
- Modify: `apps/backend/joggy/worker/tasks.py`

- [ ] **Step 1: Read current tasks.py lines 1–55** (already done during planning — verify structure)

- [ ] **Step 2: Replace the process_photo skeleton**

Replace the entire `process_photo()` function in `apps/backend/joggy/worker/tasks.py` (lines 34–52) with:

```python
# ── Module-level ONNX session singleton ───────────────────────────────────────
# Loaded once when the RQ worker process starts.
# None initially — populated on first call (lazy load to avoid import at module level).
_sessions: "ModelSessions | None" = None  # type: ignore[assignment]


def _get_sessions() -> "ModelSessions":
    """Return preloaded ONNX sessions — load on first call (worker startup)."""
    global _sessions
    if _sessions is None:
        import os
        from joggy.ai.session import load_sessions, ModelSessions
        model_dir = os.environ.get("MODEL_DIR", "models")
        logger.info("Loading ONNX sessions from %s ...", model_dir)
        _sessions = load_sessions(model_dir)
        logger.info("ONNX sessions loaded OK")
    return _sessions


# ── Phase 3: Photo AI pipeline ────────────────────────────────────────────────

async def _process_photo_async(photo_id: str, sessions: "ModelSessions") -> dict:
    """Async wrapper — creates DB session and calls pipeline.run_pipeline()."""
    from joggy.worker.pipeline import run_pipeline
    async with worker_db_session() as db:
        return await run_pipeline(photo_id, db, sessions)


def process_photo(photo_id: str) -> dict:
    """
    RQ job entrypoint — AI pipeline for 1 photo.
    Preloads ONNX sessions on first call (worker startup).
    On failure: logs + re-raises (RQ will retry up to job_timeout).
    """
    sessions = _get_sessions()
    try:
        return asyncio.run(_process_photo_async(photo_id, sessions))
    except Exception:
        logger.exception("process_photo FAILED: photo_id=%s", photo_id)
        raise
```

Also add the `ModelSessions` type hint import at the top of the file (inside `TYPE_CHECKING` block):

```python
from __future__ import annotations

# ... existing imports ...
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from joggy.ai.session import ModelSessions
```

- [ ] **Step 3: Verify import chain works**

```bash
cd apps/backend
uv run python -c "from joggy.worker.tasks import process_photo; print('import OK')"
```

Expected: `import OK` (no ModuleNotFoundError)

- [ ] **Step 4: Run all AI + pipeline tests together**

```bash
uv run pytest tests/ai/ tests/worker/test_pipeline.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add apps/backend/joggy/worker/tasks.py
git commit -m "feat(ai): implement process_photo() with ONNX pipeline + session singleton"
```

---

## Task 8: Export scripts + models/ placeholder + .gitignore

**Files:**
- Create: `apps/backend/models/.gitkeep`
- Create: `apps/backend/.gitignore`
- Create: `tools/export/export_yolo.py`
- Create: `tools/export/export_ocr.py`

- [ ] **Step 1: Create `apps/backend/.gitignore`**

```
# ONNX model files — baked into Docker image, not committed to git
# Populate via: make download-models OR copy manually
models/*.onnx
models/buffalo_s/
```

- [ ] **Step 2: Create `apps/backend/models/.gitkeep`**

Empty file — ensures `models/` directory exists in repo.

```bash
mkdir apps/backend/models apps/backend/models/buffalo_s
touch apps/backend/models/.gitkeep apps/backend/models/buffalo_s/.gitkeep
```

- [ ] **Step 3: Create `tools/export/export_yolo.py`**

```python
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

MODEL_WEIGHTS = "yolov8n.pt"   # replace with fine-tuned .pt if available
OUTPUT_DIR = Path("apps/backend/models")

print(f"Loading {MODEL_WEIGHTS} ...")
model = YOLO(MODEL_WEIGHTS)

print("Exporting to ONNX (imgsz=640, simplify=True) ...")
model.export(format="onnx", imgsz=640, simplify=True, opset=17)

src = Path("yolov8n.onnx")
dst = OUTPUT_DIR / "yolov8n_bib.onnx"
shutil.move(str(src), str(dst))
print(f"Saved: {dst}")
print("Done. Verify tensor names before running worker.")
```

- [ ] **Step 4: Create `tools/export/export_ocr.py`**

```python
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
```

- [ ] **Step 5: Create InsightFace download instructions**

Create `apps/backend/models/README.md`:

```markdown
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
```

- [ ] **Step 6: Commit**

```bash
git add apps/backend/.gitignore apps/backend/models/ tools/export/
git commit -m "feat(ai): export scripts + models/ placeholder + .gitignore"
```

---

## Final verification

- [ ] **Run full test suite**

```bash
cd apps/backend
uv run pytest tests/ -v
```

Expected: all tests pass (no failures)

- [ ] **Verify import chain end-to-end**

```bash
uv run python -c "
from joggy.ai.session import ModelSessions
from joggy.ai.bib_detector import BibDetector, BibBox
from joggy.ai.bib_ocr import BibOcr, BibResult
from joggy.ai.face_embedder import FaceEmbedder, FaceResult
from joggy.worker.pipeline import run_pipeline, _BIB_CONF_THRESHOLD
from joggy.worker.tasks import process_photo
print('All imports OK')
print(f'BIB_CONF_THRESHOLD = {_BIB_CONF_THRESHOLD}')
"
```

Expected:
```
All imports OK
BIB_CONF_THRESHOLD = 0.7
```

---

## Self-review notes for implementer

1. **Tensor names** — verify with `session.get_inputs()[0].name` after loading real model files. The names in this plan (`"images"`, `"x"`, `"input.1"`, `"683"`) are standard defaults; they may differ if models were exported with custom names.

2. **YOLOv8 output format** — if using pretrained COCO weights (80 classes), output shape is `(1, 84, 8400)`. Confidence for single-class is `preds[:, 4]` (max class score). For fine-tuned 1-class model it's `preds[:, 4]` directly.

3. **pgvector CAST syntax** — if `CAST(:vec AS vector)` fails with asyncpg, try `':vec'::vector` or pass the vector as `numpy.ndarray` directly with pgvector's registered type adapter.

4. **`event.end_at` timezone** — if `event.end_at` has no tzinfo, `replace(tzinfo=timezone.utc)` handles it safely. Use `aware_end_at = event.end_at if event.end_at.tzinfo else event.end_at.replace(tzinfo=timezone.utc)`.
