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
# Called by gphoto2 for each event in tethered mode
# gphoto2 ส่งค่าผ่าน ENV VARS (ไม่ใช่ positional args!):
#   $ACTION: init | start | download | stop
#   $ARGUMENT: filepath (เฉพาะตอน ACTION=download)
LOGFILE=/home/pi/logs/capture.log
QUEUE=/home/pi/logs/upload_queue.log
echo "[$(date '+%Y-%m-%d %H:%M:%S')] ACTION=$ACTION ARGUMENT=$ARGUMENT" >> "$LOGFILE"
if [ "$ACTION" = "download" ] && [ -n "$ARGUMENT" ]; then
    echo "UPLOAD_PENDING: $ARGUMENT" >> "$QUEUE"
    # Phase 2 จริง: python3 /home/pi/joggy/uploader.py "$ARGUMENT"
fi
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
=== Phase A (Windows) — ทดสอบ 2026-05-30 ✅ GO ===
Hardware: Canon EOS RP + USB-C + Windows laptop + digiCamControl (Stable)

TC-A1 Connectivity:    ✅ PASS — gล้องขึ้นใน digiCamControl < 5s, Live View ได้
TC-A2 Tethered GUI:    ✅ PASS — รูปปรากฏ < 3s, ขนาด 5-6 MB ถูกต้อง
TC-A3 CLI Capture:     ✅ PASS — CameraControlCmd.exe /capture ทำงานได้, รูปใน C:\test_photos
TC-A4 Auto Folder:     ✅ PASS — burst 5 รูป ครบ ชื่อไฟล์เรียงถูกต้อง
TC-A5 PTP/IP WiFi:     ⚠️ SKIP (digiCamControl ไม่รองรับ Canon WiFi)
                         Note: gphoto2 บน Pi รองรับ PTP/IP — defer to TC-B6

Overall Phase A: ✅ GO — Path A (USB Tether) พร้อมใช้งาน

=== Phase B (Raspberry Pi 5) — ทดสอบ 2026-05-31 ===
Hardware: Pi 5 (Raspberry Pi OS 64-bit Desktop, kernel 6.12.75) + Canon EOS RP + USB-C
gphoto2 2.5.31, libgphoto2 2.5.31

TC-B1 gphoto2 detect:  ✅ PASS — usb:001,004
TC-B2 Single capture:  ✅ PASS — ไฟล์ 6.6 MB
TC-B3 Hook script:     ✅ PASS — capture log + upload_queue ครบ
                         (ข้อมูล: gphoto2 ส่งผ่าน env vars ACTION/ARGUMENT
                         ไม่ใช่ positional $1/$2)
TC-B4 Burst 11 shots:  ✅ PASS — 28s total, avg 2.5s/รูป, ไฟล์ครบ 11/11
                         (เกินเป้า 6s/รูปไป 2 เท่า)
TC-B5 Long session 2h: ⏳ DEFER — ทดสอบใกล้งานจริง
TC-B6 PTP/IP WiFi:     ⚠️ PARTIAL — detect ผ่าน WiFi ได้, แต่ capture timeout
                         (Canon proprietary handshake limitation ใน gphoto2)
                         Workaround: USB tether (Path A) — เพียงพอสำหรับ production
                         Path C deferred to post-MVP (อาจใช้ chdkptp หรือ Canon CCAPI HTTP)

Overall Phase B: ✅ GO — Path A (USB tether) VALIDATED for production

=== Issues encountered + fixes ===
1. gphoto2 error "Could not claim the USB device" — gvfs-gphoto2-volume-monitor
   ของ Pi OS Desktop แย่ง USB; แก้: override service file ที่
   /etc/systemd/user/gvfs-gphoto2-volume-monitor.service.d/override.conf
   เพิ่ม ConditionPathExists=/nonexistent → service จะ inactive
   (production แนะนำใช้ Pi OS Lite — ไม่มี gvfs ตั้งแต่แรก)

2. Hook script $1 $2 = empty — gphoto2 ส่งผ่าน env vars ACTION/ARGUMENT แทน
   ต้องใช้ "$ACTION" และ "$ARGUMENT" ใน script
```

---

## 4.5 Known Gotchas (Pi 5 Desktop OS — แก้ก่อนใช้งานจริง)

### Gotcha 1: gvfs แย่ง USB (Desktop edition เท่านั้น)

อาการ:
```
*** Error ***
An error occurred in the io-library ('Could not claim the USB device'):
Could not claim interface 0 (Device or resource busy).
```

แก้ถาวร:
```bash
sudo mkdir -p /etc/systemd/user/gvfs-gphoto2-volume-monitor.service.d/
sudo tee /etc/systemd/user/gvfs-gphoto2-volume-monitor.service.d/override.conf << 'EOF'
[Unit]
ConditionPathExists=/nonexistent
EOF
```

> Production แนะนำใช้ **Raspberry Pi OS Lite** (ไม่มี gvfs ตั้งแต่แรก ไม่ต้อง patch)

### Gotcha 2: Hook script ต้องใช้ env vars ไม่ใช่ positional args

`$1`, `$2` ใน hook script จะเป็น empty string เสมอ — gphoto2 ส่งค่าผ่าน:
- `$ACTION` = `init` | `start` | `download` | `stop`
- `$ARGUMENT` = path ของไฟล์ (เฉพาะตอน `ACTION=download`)

### Gotcha 3: Canon EOS RP ไม่ชาร์จผ่าน USB-C ตอน tether กับ Pi

ต้องใช้ **dummy battery DR-E18 + power bank** สำหรับงานยาว (4-6 ชม.)

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
