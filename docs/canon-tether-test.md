# Canon EOS RP — Tethered Capture Test Plan

> **เอกสารนี้แทนที่ `canon-ftp-test.md` ทั้งหมด**
>
> ยืนยันแล้ว: Canon EOS RP **ไม่มี FTP client** ในกล้อง (FTP มีเฉพาะ pro body: R5, R6 II, 5D IV)
> ทางเลือกหลัก: **USB Tether + gphoto2** | ทางเลือกรอง: **PTP/IP over WiFi + gphoto2**

วันที่แก้ไข: 2026-05-29

---

## 0. สมมติฐานที่ต้องพิสูจน์

| # | สมมติฐาน | สำคัญแค่ไหน |
|---|---|---|
| H1 | Canon EOS RP รองรับ USB tether ผ่าน gphoto2 | 🔴 critical (Path A) |
| H2 | gphoto2 รับรูปได้ภายใน 2 วินาที/รูปหลังกดชัตเตอร์ | 🟡 performance |
| H3 | gphoto2 `--capture-tethered` รัน continuous ได้นาน 2+ ชม. โดยไม่ crash | 🔴 critical |
| H4 | PTP/IP WiFi (Canon PC Remote via WiFi) + gphoto2 ทำงานได้ | 🟢 nice-to-have (Path C) |
| H5 | hook script ทำงานถูกต้องทุกครั้งที่รูปเข้า | 🔴 critical |

---

## 1. อุปกรณ์

### Phase A — ทดสอบบน Windows Laptop (ตอนนี้ Pi ยังไม่มา)

- [ ] Canon EOS RP + เลนส์ + แบตเตอรี่เต็ม
- [ ] สาย USB-C (หรือ USB-A to USB-C)
- [ ] Windows laptop (ที่ใช้งานอยู่)
- [ ] digiCamControl (ติดตั้งก่อนทดสอบ)

### Phase B — ทดสอบบน Raspberry Pi 5 (เมื่อ Pi ถึงมือ)

- [ ] Raspberry Pi 5 (แนะนำ 4 GB+ RAM)
- [ ] microSD 64 GB+ (A2)
- [ ] สาย USB-C ยาว 2 เมตร (USB 3.0 ดีกว่า)
- [ ] Power supply Pi (official USB-C 27W)
- [ ] Dummy battery Canon EOS RP (DR-E6 compatible)

---

## 2. Phase A — ทดสอบบน Windows (ก่อน Pi มาถึง)

### ติดตั้ง digiCamControl

1. Download ฟรีที่ http://digicamcontrol.com/
2. ติดตั้ง (Windows installer)
3. เสียบ Canon EOS RP ด้วย USB-C
4. กล้อง: **Menu → Communication Settings → USB Connection → PC Connect (EOS Utility)**
5. เปิด digiCamControl → กล้องควรขึ้นชื่อใน camera list

### TC-A1 — Connectivity

- [ ] digiCamControl ตรวจพบกล้อง
- [ ] เห็น Live View ได้
- **Pass:** กล้องขึ้นใน software ภายใน 10 วินาที
- **Fail:** ลองเปลี่ยน USB mode ในกล้อง → `PTP` แทน `PC Connect`

### TC-A2 — Tethered Capture (GUI)

- [ ] กดชัตเตอร์ที่กล้อง → รูปปรากฏใน digiCamControl โดยอัตโนมัติ
- [ ] รูปถูก save ลง folder ที่กำหนดใน Session settings
- **Pass:** รูปปรากฏภายใน 3 วินาที + ขนาดถูกต้อง (~25 MB RAW หรือ ~5 MB JPEG)
- **Record:** เวลา (capture → file บน disk)

### TC-A3 — CLI Capture

```cmd
:: เปิด Command Prompt ที่ folder ของ CameraControlCmd.exe
CameraControlCmd.exe /capture /folder "C:\test_photos"
```

- [ ] รัน command → รูปปรากฏใน `C:\test_photos\`
- **Pass:** exit code 0 + file exists
- **Note:** CLI นี้คือ proof-of-concept สำหรับ automation — Pi จะใช้ gphoto2 แทน

### TC-A4 — Auto Folder Watch (simulation)

- [ ] ตั้ง digiCamControl Session → Auto download to folder
- [ ] ถ่ายต่อเนื่อง 5 รูป
- [ ] ตรวจว่าทุกรูปอยู่ใน folder ครบ
- **Pass:** 5/5 รูปปรากฏ, ไม่มี duplicate/missing

### TC-A5 — PTP/IP WiFi (Path C test บน Windows)

- [ ] กล้อง: **Menu → WiFi/Bluetooth Settings → EOS Utility via WiFi**
- [ ] กล้องแสดง IP address ที่ได้รับ
- [ ] digiCamControl → Add camera → ใส่ IP ของกล้อง
- **Pass:** connect ได้ + tethered capture ทำงาน
- **Fail:** skip Path C → Path A USB only

---

## 3. Phase B — ทดสอบบน Raspberry Pi 5 (เมื่อ Pi มาถึง)

### Pi Setup

```bash
# OS: Raspberry Pi OS Lite 64-bit (Bookworm)
sudo apt update && sudo apt upgrade -y

# gphoto2 + inotify
sudo apt install -y gphoto2 libgphoto2-dev inotify-tools python3-pip python3-venv

# uv (D-010)
curl -LsSf https://astral.sh/uv/install.sh | sh

# สร้าง folder สำหรับรูป
mkdir -p /home/pi/photos/inbox
```

### TC-B1 — gphoto2 Detect Camera

```bash
# เสียบ Canon EOS RP ด้วย USB-C
gphoto2 --auto-detect
```

Expected output:
```
Model                          Port
----------------------------------------------------------
Canon EOS RP                   usb:001,004
```

- **Pass:** ชื่อกล้องขึ้น
- **Fail:** ลอง `sudo gphoto2 --auto-detect` (permission issue)

### TC-B2 — Single Capture

```bash
gphoto2 --capture-image-and-download --filename /home/pi/photos/test_%n.jpg
```

- [ ] ไฟล์ปรากฏใน `/home/pi/photos/`
- **Pass:** file exists + ขนาดถูกต้อง

### TC-B3 — Tethered Capture + Hook Script

สร้าง hook script `/home/pi/joggy/on_photo.sh`:

```bash
#!/bin/bash
# Called by gphoto2 after each capture
# $1 = filepath of downloaded image
FILEPATH="$1"
if [ -z "$FILEPATH" ]; then exit 0; fi

echo "[$(date)] New photo: $FILEPATH" >> /home/pi/logs/capture.log

# Phase 2: trigger actual upload
# python3 /home/pi/joggy/uploader.py "$FILEPATH"

# Phase A test: just log
echo "UPLOAD_PENDING: $FILEPATH" >> /home/pi/logs/upload_queue.log
```

```bash
chmod +x /home/pi/joggy/on_photo.sh

# รัน tethered mode
gphoto2 --capture-tethered \
        --hook-script /home/pi/joggy/on_photo.sh \
        --filename "/home/pi/photos/inbox/%Y%m%d_%H%M%S.jpg"
```

- [ ] กดชัตเตอร์กล้อง → รูปปรากฏใน `/home/pi/photos/inbox/`
- [ ] `capture.log` มีบรรทัดใหม่
- **Pass:** hook ถูกเรียกทุกครั้ง + filename timestamp ถูกต้อง

### TC-B4 — Burst Test (H2 + H3)

```bash
# รัน tethered ค้างไว้
gphoto2 --capture-tethered --hook-script /home/pi/joggy/on_photo.sh \
        --filename "/home/pi/photos/inbox/%Y%m%d_%H%M%S_%n.jpg" &

# ถ่าย 10 รูปในเวลา ~30 วินาที
# แล้วตรวจ
ls -la /home/pi/photos/inbox/ | wc -l
```

- **Pass:** 10 ไฟล์ครบ ภายใน 60 วินาที
- **Record:** เวลาเฉลี่ย + สูงสุดต่อรูป

### TC-B5 — Long Session Stability (H3)

```bash
# รัน 2 ชั่วโมง ถ่ายทุก ~30 วินาที (ประมาณ 240 รูป)
gphoto2 --capture-tethered --hook-script /home/pi/joggy/on_photo.sh \
        --filename "/home/pi/photos/inbox/%Y%m%d_%H%M%S.jpg"

# monitor ใน terminal แยก
watch -n5 'ls /home/pi/photos/inbox/ | wc -l; free -m; top -bn1 | head -5'
```

- **Pass:** ไม่ crash, RAM stable, count เพิ่มขึ้นเรื่อยๆ
- **Record:** RAM peak, CPU average

### TC-B6 — PTP/IP WiFi ผ่าน gphoto2 (Path C — Pi version)

```bash
# กล้อง: WiFi Settings → EOS Utility via WiFi → note the IP
# ตั้งให้ Pi + กล้องอยู่ใน WiFi network เดียวกัน

gphoto2 --port ptpip:192.168.x.x --auto-detect

# ถ้า detect ได้:
gphoto2 --port ptpip:192.168.x.x \
        --capture-tethered \
        --hook-script /home/pi/joggy/on_photo.sh \
        --filename "/home/pi/photos/inbox/%Y%m%d_%H%M%S.jpg"
```

- **Pass:** connect ได้ + รูปเข้าเหมือน USB
- **Fail action:** Path C = experimental, ใช้ USB (Path A) แทน

---

## 4. Result Template

```
ทดสอบเมื่อ: ___
Phase: A (Windows laptop) / B (Raspberry Pi 5)
Hardware:
  - Canon EOS RP firmware: ___
  - Pi 5 RAM: ___ GB (Phase B only)
  - สาย USB: ___

=== Phase A (Windows) ===
TC-A1 Connectivity:    PASS / FAIL — note: ___
TC-A2 Tethered GUI:    PASS / FAIL — latency: ___s
TC-A3 CLI Capture:     PASS / FAIL — note: ___
TC-A4 Auto Folder:     PASS / FAIL — 5/5 files: ___
TC-A5 PTP/IP WiFi:     PASS / FAIL / SKIP

=== Phase B (Pi 5) ===
TC-B1 gphoto2 detect:  PASS / FAIL
TC-B2 Single capture:  PASS / FAIL
TC-B3 Hook script:     PASS / FAIL
TC-B4 Burst 10 shots:  PASS / FAIL — avg: ___s, max: ___s
TC-B5 Long session 2h: PASS / FAIL — RAM peak: ___ MB
TC-B6 PTP/IP WiFi:     PASS / FAIL / SKIP

Overall Phase A: GO / NO-GO
Overall Phase B: GO / NO-GO

Issues:
- ___
```

---

## 5. Risk Mitigation

| ความเสี่ยง | Mitigation |
|---|---|
| กล้องไม่ขึ้นใน gphoto2 | ลอง `sudo`, ตรวจ USB mode ในกล้อง (PTP ไม่ใช่ MTP) |
| สาย USB-C ยาวเกิน 2m ทำให้ช้า | ใช้ USB 3.0 active extension cable หรือ USB hub powered |
| กล้องหยุดตอบสนองหลัง sleep | ตั้ง Auto power off → Disable ในกล้อง |
| Pi overheat ในสนาม | heatsink + shade + active cooling ถ้าจำเป็น |
| แบต Canon หมดระหว่างงาน | dummy battery (DR-E6 compatible + power bank) |
| Path C (WiFi) unstable | fallback Path A USB เสมอ |

---

## 6. Next Steps

### Phase A GO (Windows ทดสอบผ่าน):
- รอ Pi 5 มาถึง → ทำ Phase B

### Phase A NO-GO:
- ตรวจ USB mode ในกล้อง (กล้อง → Communication Settings → USB Connection → ลอง PTP)
- ลองติดตั้ง Canon EOS Utility แทน digiCamControl เพื่อ verify connectivity ก่อน

### Phase B GO:
- Implement `apps/edge/` watchdog uploader ใน Python (Phase 1 backlog)
- Integration test Pi → VPS

### Path C GO (WiFi PTP/IP ทำงาน):
- บันทึกใน DECISIONS.md เป็น D-002 Path C
- ประเมิน latency vs USB ก่อนเลือก primary ในงานจริง
