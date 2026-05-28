# Dependency & Research Check สำหรับ AI Stack

> **จัดทำโดย:** Antigravity (Flex Agent)
> **วันที่:** 2026-05-28
> **วัตถุประสงค์:** ตรวจสอบความพร้อมของ dependency สำหรับ AI stack บนสภาพแวดล้อมต่างๆ (Windows 11, Linux x86_64, Linux ARM64) และประเมิน RAM ตามสมมติฐานใน ADR-0003

---

## 1. การติดตั้ง `uv` (Package Manager)

- **Windows 11 (dev environment):** ✅ **OK**
  - รองรับระดับ Tier 1 สำหรับ x86_64 และ Tier 2 สำหรับ ARM64
  - วิธีติดตั้ง: `powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"` หรือผ่าน `winget`
- **Linux x86_64 (Hetzner CPX11):** ✅ **OK**
  - รองรับระดับ Tier 1 
  - วิธีติดตั้ง: `curl -LsSf https://astral.sh/uv/install.sh | sh`
- **Linux ARM64 (Raspberry Pi 5):** ✅ **OK**
  - รองรับระดับ Tier 2 (aarch64) โหลดได้ผ่าน script เดียวกับ Linux ปกติ

---

## 2. การรองรับ Wheel สำหรับ AI Libraries

### 2.1 Ultralytics (YOLOv8)
- **Linux x86_64:** ✅ **OK** (มี wheel ปกติของ PyTorch CPU)
- **Linux ARM64:** ⚠️ **Issue**
  - ไม่มี "ARM64 wheel" แบบเฉพาะเจาะจงจาก Ultralytics แต่มันใช้ `torch` และ `torchvision` ซึ่งมี wheel บน ARM64 (aarch64) ให้โหลดผ่าน pip 
  - **Workaround:** ต้องติดตั้ง `torch` CPU-only ก่อน แล้วค่อยลง `ultralytics` หรือใช้ official Docker image `ultralytics/ultralytics:latest-arm64` เพื่อป้องกันปัญหา library C++ 

### 2.2 PaddlePaddle + PaddleOCR
- **Linux x86_64:** ✅ **OK**
- **Linux ARM64:** ❌ **Blocker**
  - ไม่มี official wheel ของ PaddlePaddle สำหรับ Linux ARM64 ผ่าน `pip install` หากติดตั้งมักจะ error หรือ Segmentation fault
  - **Workaround:** 
    1. Compile จาก source (ซึ่งเสี่ยงและใช้เวลานานมาก ไม่แนะนำบน Pi 5)
    2. หากจำเป็นต้องรันบน ARM64 จริงๆ ควร Export โมเดลจาก PaddleOCR เป็น **ONNX** แล้วใช้ `onnxruntime` รันแทน

### 2.3 InsightFace + ONNXRuntime
- **Linux x86_64:** ✅ **OK**
- **Linux ARM64:** ⚠️ **Issue**
  - `onnxruntime` มี wheel บน aarch64 ปกติ
  - แต่ `insightface` อาจพยายาม compile C++ extension (`face3d`) ตอนติดตั้งผ่าน pip บน ARM64
  - **Workaround:** ต้องติดตั้ง `build-essential`, `python3-dev` และ `libopencv-dev` ก่อนติดตั้ง `insightface` (แนะนำใช้เวอร์ชัน 1.0+ เพื่อข้ามการบิลด์ `face3d`)

---

## 3. ขนาดของโมเดล InsightFace (`buffalo_s`)

- **ขนาดไฟล์ดาวน์โหลด:** ~159 MB
- **URL สำหรับดาวน์โหลด:**
  - โหลดอัตโนมัติผ่าน code: `FaceAnalysis(name='buffalo_s')` 
  - Manual download ได้ที่ Model Zoo บน GitHub ของ `deepinsight/insightface` (นำไฟล์ไปวางที่ `~/.insightface/models/`)

---

## 4. ประเมิน RAM Usage (เทียบกับ ADR-0003)

ใน [ADR-0003](../docs/adr/0003-single-ai-worker-process.md) มีสมมติฐานว่า YOLOv8-nano + PaddleOCR + InsightFace จะใช้ RAM **~900 MB ต่อ process**

จากข้อมูลที่รวบรวมได้เมื่อโหลดโมเดลเข้าสู่ Memory พร้อมกัน:
- **YOLOv8-nano:** ใช้ RAM ประมาณ **400 - 600 MB** (Overhead ของ PyTorch framework ค่อนข้างสูง)
- **PaddleOCR (Eng/Number):** ใช้ RAM ประมาณ **500 - 1,000 MB** (เฉพาะ base memory ตอนโหลด PaddlePaddle framework)
- **InsightFace (`buffalo_s`):** ตัวโมเดลมีขนาด 159 MB แต่อาจใช้ RAM ประมาณ **200 - 300 MB** เมื่อบวก Overhead ของ ONNXRuntime

🔴 **รวม RAM Estimate ทั้งหมด:** ประมาณ **1,100 MB - 1,900 MB** 
(หากใช้งาน PyTorch + PaddlePaddle + ONNXRuntime พร้อมกันใน 1 Process ตัว Framework Overhead จะแย่งพื้นที่ Memory ไปจำนวนมาก)

---

## 5. ความเสี่ยงด้าน Installation & Dependency

1. **Framework Overhead:** การใช้ PyTorch (YOLO), PaddlePaddle (OCR) และ ONNXRuntime (InsightFace) พร้อมกัน ทำให้โหลด dependency หนักมาก และเสี่ยงกิน RAM ทะลุ `mem_limit: 1200m` ที่ตั้งไว้ใน ADR-0003
2. **GLIBC / libgl / libopencv:** บน VPS และ Pi จำเป็นต้องมี `libgl1` และ `libglib2.0-0` (หรือ `libopencv-dev` บน ARM64) เพื่อให้ OpenCV ทำงานได้ ถ้าเป็น Docker container ต้องสั่ง `apt-get install` 
3. **CUDA-only wheels:** บางครั้ง pip ฝั่ง Linux จะพยายามโหลด CUDA wheel (ที่มีขนาดใหญ่เป็น GB) ให้ระบุ index-url เป็น CPU-only (`--extra-index-url https://download.pytorch.org/whl/cpu`) เพื่อป้องกันปัญหาขนาด image และแรมบวม

---

## 💡 Recommendation เสนอต่อ Claude (Tech Lead)

1. **ปรับปรุง ADR-0003 (RAM Budget):** 
   - สมมติฐานที่ 900 MB **เสี่ยง OOM อย่างมาก** เนื่องจาก PaddlePaddle + PyTorch ซ้อนกัน
   - **เสนอแนะ:** ควร Export ทั้งโมเดล YOLOv8-nano และ PaddleOCR ไปเป็นรูปแบบ **ONNX** เพื่อให้ทั้ง Pipeline โหลดเพียง **ONNXRuntime** ตัวเดียว (รวมกับ InsightFace) วิธีนี้จะช่วยลด Overhead ของ Framework จากหลัก GB เหลือเพียงไม่กี่ร้อย MB ช่วยการันตีความปลอดภัยภายใต้ RAM < 1200MB ของ CPX11 แน่นอน
2. **ปรับปรุง ADR-0001 / Architecture:**
   - ในการเขียนโค้ดสำหรับ Edge (Raspberry Pi 5) หากจำเป็นต้องรัน YOLOv8-nano เพื่อจับ Motion อย่าหลงไปลง PaddlePaddle เด็ดขาด และให้ระวังการลง PyTorch บน ARM64 เพราะอาจพังได้ง่าย เสนอให้ใช้ ONNXRuntime / NCNN บน Pi 5 สำหรับงาน Edge จะเสถียรกว่า

# Antigravity: Research ข้อมูล Dependency สำหรับ AI Pipeline, ตรวจสอบสถานะการรองรับ ARM64/x86_64 ของไลบรารีต่างๆ และประเมินการใช้งาน RAM พร้อมแจ้งเตือนความเสี่ยงเกี่ยวกับสมมติฐาน RAM budget ของ ADR-0003
