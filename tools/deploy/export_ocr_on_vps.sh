#!/usr/bin/env bash
# One-shot OCR ONNX export — runs paddlepaddle inside Docker on the VPS so
# we don't have to install Paddle on Windows or pollute the production
# worker image with training dependencies.
#
# Usage (run as joggy@joggy-prod-01):
#   bash /opt/joggy-picx/tools/deploy/export_ocr_on_vps.sh
#
# Result: ocr_rec.onnx + ocr_det.onnx + en_dict.txt under
# /opt/joggy-picx/apps/backend/models/ (the path the worker mounts read-only).
#
# After this script, restart the worker:
#   docker compose -f /opt/joggy-picx/infra/docker-compose.yml \
#                  -f /opt/joggy-picx/infra/docker-compose.prod.yml \
#                  restart worker
#
# Author: Claude (Tech Lead) — Phase 6 OCR enablement, 2026-06-11

set -euo pipefail

MODELS_DIR="/opt/joggy-picx/apps/backend/models"
WORK_DIR=$(mktemp -d -t joggy-ocr-XXXXXXXX)
trap 'rm -rf "$WORK_DIR"' EXIT

PADDLE_IMAGE="paddlepaddle/paddle:3.0.0"
# As of 2026-06-11 the EN det tar returns 404 from the BCE bucket while
# the CN det tar is fine. The CN vocab (6625 chars) is filtered down to
# digits in bib_ocr.py anyway, so accuracy on bib numbers is unaffected.
# If the EN tar comes back, you can swap REC_TAR_URL + DICT_URL and the
# rest of the pipeline keeps working.
REC_TAR_URL="https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_rec_infer.tar"
DET_TAR_URL="https://paddleocr.bj.bcebos.com/PP-OCRv4/chinese/ch_PP-OCRv4_det_infer.tar"
REC_DIR_NAME="ch_PP-OCRv4_rec_infer"
DET_DIR_NAME="ch_PP-OCRv4_det_infer"
DICT_URL="https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/main/ppocr/utils/ppocr_keys_v1.txt"
DICT_FILE="ppocr_keys_v1.txt"

echo "[ocr-export] Working in $WORK_DIR"
echo "[ocr-export] Downloading $DICT_FILE (vocab)..."
curl -fsSL "$DICT_URL" -o "$WORK_DIR/$DICT_FILE"
wc -l "$WORK_DIR/$DICT_FILE"

echo "[ocr-export] Downloading rec model tar on host (Docker network has DNS quirks)..."
curl -fsSL "$REC_TAR_URL" -o "$WORK_DIR/rec.tar"
echo "[ocr-export] Downloading det model tar on host..."
curl -fsSL "$DET_TAR_URL" -o "$WORK_DIR/det.tar"
ls -lh "$WORK_DIR"

echo "[ocr-export] Pulling paddlepaddle image (one-shot)..."
docker pull "$PADDLE_IMAGE"

echo "[ocr-export] Running export inside container (network kept for pip)..."
# Use --dns 8.8.8.8 because the paddlepaddle image's resolv.conf occasionally
# resolves bcebos.com to wrong AS path — but we've already downloaded the
# tars on the host, so pip is the only thing that needs network here.
docker run --rm \
  --dns 8.8.8.8 \
  -v "$WORK_DIR:/work" \
  -w /work \
  "$PADDLE_IMAGE" \
  bash -c "
    set -e
    pip install --quiet paddle2onnx==1.2.6
    tar -xf rec.tar
    tar -xf det.tar
    paddle2onnx \\
      --model_dir $REC_DIR_NAME \\
      --model_filename inference.pdmodel \\
      --params_filename inference.pdiparams \\
      --save_file ocr_rec.onnx \\
      --opset_version 11 \\
      --enable_onnx_checker True
    paddle2onnx \\
      --model_dir $DET_DIR_NAME \\
      --model_filename inference.pdmodel \\
      --params_filename inference.pdiparams \\
      --save_file ocr_det.onnx \\
      --opset_version 11 \\
      --enable_onnx_checker True
    ls -lh ocr_rec.onnx ocr_det.onnx
  "

echo "[ocr-export] Installing into $MODELS_DIR ..."
sudo install -m 644 -o joggy -g joggy \
  "$WORK_DIR/ocr_rec.onnx" "$MODELS_DIR/ocr_rec.onnx"
sudo install -m 644 -o joggy -g joggy \
  "$WORK_DIR/ocr_det.onnx" "$MODELS_DIR/ocr_det.onnx"
sudo install -m 644 -o joggy -g joggy \
  "$WORK_DIR/$DICT_FILE" "$MODELS_DIR/$DICT_FILE"

ls -lh "$MODELS_DIR/ocr_rec.onnx" "$MODELS_DIR/ocr_det.onnx" "$MODELS_DIR/$DICT_FILE"

cat <<NEXT

[ocr-export] Done!

Next steps:
  1. Set OCR_VOCAB_PATH in the worker environment so bib_ocr.py can decode
     the rec output. Edit /opt/joggy-picx/.env.production and add:
       OCR_VOCAB_PATH=/app/apps/backend/models/$DICT_FILE
  2. Rebuild + restart the worker so it picks up the new vocab + models:
       cd /opt/joggy-picx/infra
       docker compose -f docker-compose.yml -f docker-compose.prod.yml \\
                      up -d --build worker
  3. Take one photo from the Pi and watch the worker log — you should see
     "Loaded 5/5 ONNX sessions" and a real bib_number on the dashboard.

NEXT
