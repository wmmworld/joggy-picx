# Canon EOS RP → Raspberry Pi 5 — FTP Test Plan

> เอกสารนี้คือ **test plan ภาคสนาม** สำหรับยืนยันสมมติฐานสำคัญ:
> Canon EOS RP สามารถส่งรูปผ่าน WiFi FTP เข้า Raspberry Pi 5 ใน LAN เดียวกันได้
> ทดสอบนี้คือ **gate ของ Phase 1** — ถ้าผ่าน → continue; ถ้าไม่ผ่าน → revisit D-002 (Pi เป็น REQUIREMENT)
> CEO ทดสอบเองภาคสนาม + รายงานผลกลับ Claude

วันที่: 2026-05-28 (Phase 1 Day 2)

---

## 0. สมมติฐานที่ต้องพิสูจน์

| # | สมมติฐาน | สำคัญแค่ไหน |
|---|---|---|
| H1 | Canon EOS RP รองรับ FTP upload ใน LAN ผ่าน WiFi | 🔴 critical |
| H2 | Pi 5 ทำ Hotspot WiFi + vsftpd พร้อมกันได้ | 🔴 critical |
| H3 | รูป JPEG (~5 MB) ส่งสำเร็จภายใน 3-5 วินาที/รูป | 🟡 nice to have |
| H4 | Canon ส่งไฟล์ที่ folder ที่กำหนด + ตั้งชื่อไฟล์ตามค่าที่ตั้ง | 🟢 verify |
| H5 | Canon retry/queue เมื่อ WiFi หลุดชั่วคราว | 🟢 verify |

ถ้า **H1 หรือ H2 fail** → ต้องเปลี่ยน ingestion path (เช่น ใช้ SD card swap) → revisit ADR-0002

---

## 1. อุปกรณ์ที่ต้องเตรียม

- [ ] Canon EOS RP (firmware update ล่าสุด)
- [ ] เลนส์ + แบตเตอรี่เต็ม + SD card
- [ ] Raspberry Pi 5 (8 GB RAM แนะนำ)
- [ ] microSD card 64 GB+ (Class 10 / A2)
- [ ] Power supply Pi (USB-C 27W ของ official) — *ทดสอบในห้อง*
- [ ] dummy battery สำหรับ Pi (test เผื่อภาคสนาม)
- [ ] WiFi USB adapter สำรอง (เผื่อ built-in WiFi ของ Pi 5 ใช้ไม่ได้)
- [ ] Notebook + LAN cable (สำหรับ debug)

---

## 2. Pi Setup (ทำครั้งแรก)

```bash
# Pi: OS = Raspberry Pi OS Lite (64-bit, Bookworm)

# Update
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y vsftpd hostapd dnsmasq python3-pip python3-venv watchdog inotify-tools

# uv (D-010)
curl -LsSf https://astral.sh/uv/install.sh | sh

# vsftpd config — ดูข้อ 3
sudo nano /etc/vsftpd.conf

# Hotspot — ดูข้อ 4
sudo nano /etc/hostapd/hostapd.conf
sudo nano /etc/dnsmasq.conf

# Restart
sudo systemctl enable --now vsftpd hostapd dnsmasq
```

---

## 3. vsftpd Config (ตัวอย่าง — `/etc/vsftpd.conf`)

```conf
listen=YES
listen_ipv6=NO

# Anonymous off — ใช้ user ที่กำหนด
anonymous_enable=NO
local_enable=YES
write_enable=YES
local_umask=022

# Restrict user to home dir
chroot_local_user=YES
allow_writeable_chroot=YES

# Passive mode (สำคัญสำหรับ Canon)
pasv_enable=YES
pasv_min_port=40000
pasv_max_port=40100
pasv_address=10.42.0.1   # IP ของ Pi ใน hotspot subnet

# Logging
xferlog_enable=YES
xferlog_file=/var/log/vsftpd.log
xferlog_std_format=YES

# Performance
local_max_rate=0   # ไม่จำกัด bandwidth ใน LAN
```

สร้าง user สำหรับ Canon:
```bash
sudo useradd -m -d /srv/ftp/canon -s /usr/sbin/nologin canon
sudo passwd canon   # ตั้งรหัสผ่านง่ายๆ ก็ได้ — เป็น LAN-only
sudo mkdir -p /srv/ftp/canon/inbox
sudo chown -R canon:canon /srv/ftp/canon
```

---

## 4. Hotspot Config (Pi เป็น Access Point)

`/etc/hostapd/hostapd.conf`:
```conf
interface=wlan0
driver=nl80211
ssid=JoggyPi-001
hw_mode=g
channel=6
wmm_enabled=1
auth_algs=1
wpa=2
wpa_passphrase=joggy-marathon-2026
wpa_key_mgmt=WPA-PSK
rsn_pairwise=CCMP
```

`/etc/dnsmasq.conf`:
```conf
interface=wlan0
dhcp-range=10.42.0.10,10.42.0.50,255.255.255.0,24h
```

`/etc/dhcpcd.conf` (เพิ่มท้ายไฟล์):
```conf
interface wlan0
    static ip_address=10.42.0.1/24
    nohook wpa_supplicant
```

---

## 5. Canon EOS RP FTP Setup

1. เมนู → Network settings → Communication settings → Connection settings
2. New → FTP transfer → Manual setup
3. SSID: `JoggyPi-001` / Password: `joggy-marathon-2026`
4. FTP server settings:
   - Address: `10.42.0.1`
   - Mode: **Passive** (สำคัญ — ตรงกับ vsftpd config)
   - Port: `21`
   - Username: `canon`
   - Password: ที่ตั้งไว้
   - Target folder: `/inbox/`
   - Overwrite same name: **OFF**
5. ทดสอบ "Confirm settings" จากกล้อง

---

## 6. Test Cases

### TC-1 — Connectivity (H1)
- [ ] Canon เชื่อม WiFi `JoggyPi-001` สำเร็จ
- [ ] Canon "Confirm settings" → ✅ Success
- **Pass criteria:** ไม่มี error
- **Fail action:** Check firewall (`ufw status`), ตรวจ vsftpd log

### TC-2 — Single Photo Upload (H1 + H4)
- [ ] ถ่ายรูป 1 รูป → กล้องส่งอัตโนมัติ (ตั้ง "Send after shot" ในกล้อง)
- [ ] ตรวจ Pi: `ls -la /srv/ftp/canon/inbox/` → เห็นไฟล์
- [ ] ตรวจ vsftpd log: `tail /var/log/vsftpd.log`
- **Pass criteria:** ไฟล์ปรากฏ + ขนาดถูกต้อง (~5 MB)
- **Record:** time delta จากกดชัตเตอร์ → ไฟล์ครบ

### TC-3 — Burst Upload (H3)
- [ ] ถ่ายต่อเนื่อง 10 รูปใน 30 วินาที
- [ ] วัดเวลา upload สำเร็จครบ
- **Pass criteria:** 10 รูป upload สำเร็จภายใน 60 วินาที (เฉลี่ย ≤6s/รูป)
- **Record:** average + max upload time

### TC-4 — WiFi Disconnect Recovery (H5)
- [ ] เริ่มถ่ายต่อเนื่อง → ระหว่างนั้นปิด Pi WiFi 10 วินาที → เปิดกลับ
- [ ] ตรวจว่ารูประหว่างที่ WiFi off → upload ภายหลังเมื่อ reconnect
- **Pass criteria:** ไม่มีรูปหาย (Canon ควรมี internal queue)
- **Fail action:** อาจต้อง configure Canon "Retry on failure" + เขียน watchdog uploader retry logic เอง

### TC-5 — Pi Watchdog Uploader (H3 ฝั่ง Pi)
- [ ] รัน watchdog script (placeholder ก่อน — Phase 1 Day 3 ค่อย implement จริง)
- [ ] ตรวจว่า script detect ไฟล์ใหม่ใน `/srv/ftp/canon/inbox/` ได้
- [ ] Script enqueue upload job ไปยัง VPS (mock endpoint ก่อน)
- **Note:** เนื้องาน watchdog uploader implement ใน Phase 1 Day 3–4

### TC-6 — Long Session (Battery + Stability)
- [ ] รัน Pi + Canon ต่อเนื่อง 2 ชั่วโมง — ทดสอบ stability
- [ ] ถ่ายทุก ~30 วินาที (ประมาณ 240 รูป)
- **Pass criteria:** ไม่มี crash, RAM ไม่รั่ว, ทุกรูป upload สำเร็จ
- **Record:** Pi RAM/CPU peak, vsftpd memory

---

## 7. Result Template (CEO กรอกกลับ)

```
ทดสอบเมื่อ: ___
สถานที่: ___
Hardware:
  - Pi 5: ___ GB RAM
  - microSD: ___
  - Canon firmware: ___

TC-1: PASS / FAIL — note: ___
TC-2: PASS / FAIL — upload time: ___s
TC-3: PASS / FAIL — avg: ___s/รูป, max: ___s/รูป
TC-4: PASS / FAIL — note: ___
TC-5: SKIP (Phase 1 Day 3+)
TC-6: PASS / FAIL — RAM peak: ___ MB

Overall: GO / NO-GO

Issues encountered:
- ___
- ___

Recommendation: ___
```

---

## 8. Risk Mitigation

| ความเสี่ยง | ที่พบ | Mitigation |
|---|---|---|
| Canon FTP active mode ไม่ work | Passive mode ใน config | ใช้ pasv_enable=YES (ทำใน TC-1) |
| WiFi 2.4GHz ในงานจริง congested | ใน open field | ใช้ 5GHz ถ้า Pi 5 wifi รองรับ |
| Pi hotspot range จำกัด | ~10-20m | กล้องต้องอยู่ในระยะ; backup = USB tether |
| Pi overheat ใน sun | กลางสนาม | heatsink + case ที่ระบายอากาศ + เก็บใน shade |
| dummy battery สำหรับ Canon | งานยาว 4-6 ชม. | ทดสอบใน TC-6, สำรองแบตเตอรี่จริง 2 ลูก |

---

## 9. Next Steps หลังทดสอบเสร็จ

### ถ้า GO:
- Phase 1 Day 3: เริ่ม implement `apps/edge/` watchdog uploader (Python)
- Phase 1 Day 4: Integration test Pi → mock VPS

### ถ้า NO-GO:
- Block Phase 1 Day 3 — emergency revisit ADR-0002
- Options:
  - SD card swap workflow (manual)
  - Canon Connect via mobile bridge
  - เปลี่ยนกล้อง (เช่น Sony A7 ที่มี FTP over LTE direct)
