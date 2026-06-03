#!/usr/bin/env bash
# =============================================================================
# Joggy-PicX — Raspberry Pi 5 Setup Script
# =============================================================================
# Idempotent: safe to run multiple times on the same Pi.
# Tested on: Raspberry Pi OS 64-bit Bookworm (Pi 5)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/wmmworld/Joggy-PicX/master/tools/setup_pi.sh | bash
#   # or after cloning:
#   bash tools/setup_pi.sh
#
# What this does:
#   1. Install system packages (gphoto2, uv, git, python3)
#   2. Install 99-joggy-canon.rules udev rule (Canon EOS RP USB permission)
#   3. Clone or update Joggy-PicX repo to /home/pi/joggy
#   4. Create Python venv via uv + install edge deps
#   5. Create photo folders (inbox, uploaded, failed)
#   6. Install joggy-edge as SYSTEM service
#   7. Install joggy-capture as USER service + enable linger
#   8. Prompt for EVENT_TOKEN + INGEST_URL → write /home/pi/joggy/.env
#   9. Enable + start both services
#  10. Smoke test: verify services running + VPS /healthz reachable
# =============================================================================

set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()      { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }
section() { echo -e "\n${BLUE}═══ $* ═══${NC}"; }

# ── Constants ─────────────────────────────────────────────────────────────────
REPO_URL="https://github.com/wmmworld/Joggy-PicX.git"
JOGGY_DIR="/home/pi/joggy"
PHOTOS_DIR="/home/pi/photos"
ENV_FILE="${JOGGY_DIR}/.env"
VENV_DIR="${JOGGY_DIR}/.venv"

# ── Sanity checks ─────────────────────────────────────────────────────────────
[[ "$(id -un)" == "pi" ]] || error "Run as user 'pi' (not root). Use: bash setup_pi.sh"
[[ "$(uname -m)" == "aarch64" ]] || warn "Expected aarch64 (Pi 64-bit), got $(uname -m) — continuing anyway"

section "Step 1: System packages"

sudo apt-get update -qq

PKGS=(gphoto2 git python3 python3-pip curl acl)
for pkg in "${PKGS[@]}"; do
    if dpkg -s "$pkg" &>/dev/null; then
        ok "$pkg already installed"
    else
        info "Installing $pkg ..."
        sudo apt-get install -y "$pkg"
        ok "$pkg installed"
    fi
done

# uv (fast Python package manager)
if command -v uv &>/dev/null; then
    ok "uv already installed ($(uv --version))"
else
    info "Installing uv ..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    ok "uv installed ($(uv --version))"
fi
# Ensure uv is on PATH for this session
export PATH="$HOME/.local/bin:$PATH"

section "Step 2: udev rule (Canon EOS RP USB permission)"

UDEV_RULE='/etc/udev/rules.d/99-joggy-canon.rules'
UDEV_CONTENT='# Joggy-PicX: Canon EOS RP — plugdev-accessible regardless of login session
SUBSYSTEM=="usb", ATTR{idVendor}=="04a9", ATTR{idProduct}=="32e2", MODE="0664", GROUP="plugdev"'

if [[ -f "$UDEV_RULE" ]] && grep -q "04a9" "$UDEV_RULE"; then
    ok "udev rule already present"
else
    echo "$UDEV_CONTENT" | sudo tee "$UDEV_RULE" > /dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger --action=change --subsystem-match=usb
    ok "udev rule installed + rules reloaded"
fi

# Ensure pi is in plugdev group
if id -nG pi | grep -qw plugdev; then
    ok "pi is in plugdev group"
else
    sudo usermod -aG plugdev pi
    warn "Added pi to plugdev — group takes effect on next login/reboot"
fi

section "Step 3: Clone / update repo"

if [[ -d "${JOGGY_DIR}/.git" ]]; then
    info "Repo already exists at ${JOGGY_DIR} — pulling latest ..."
    git -C "$JOGGY_DIR" pull --ff-only
    ok "Repo updated"
else
    info "Cloning ${REPO_URL} → ${JOGGY_DIR} ..."
    git clone "$REPO_URL" "$JOGGY_DIR"
    ok "Repo cloned"
fi

section "Step 4: Python venv + edge dependencies"

cd "${JOGGY_DIR}/apps/edge"
if [[ -d "${VENV_DIR}" ]]; then
    ok "venv already exists at ${VENV_DIR}"
else
    info "Creating venv via uv ..."
    uv venv "${VENV_DIR}" --python python3
    ok "venv created"
fi

info "Syncing edge dependencies ..."
uv sync --python "${VENV_DIR}/bin/python"
ok "Dependencies synced"

section "Step 5: Photo folders"

for dir in inbox uploaded failed; do
    path="${PHOTOS_DIR}/${dir}"
    if [[ -d "$path" ]]; then
        ok "${path} already exists"
    else
        mkdir -p "$path"
        ok "Created ${path}"
    fi
done
# Ensure pi owns all photo folders
sudo chown -R pi:pi "$PHOTOS_DIR"

section "Step 6: joggy-edge — SYSTEM service"

EDGE_SERVICE_SRC="${JOGGY_DIR}/apps/edge/infra/joggy-edge.service"
EDGE_SERVICE_DST="/etc/systemd/system/joggy-edge.service"

if [[ ! -f "$EDGE_SERVICE_SRC" ]]; then
    error "Service file not found: ${EDGE_SERVICE_SRC}"
fi

sudo cp "$EDGE_SERVICE_SRC" "$EDGE_SERVICE_DST"
sudo systemctl daemon-reload
sudo systemctl enable joggy-edge
ok "joggy-edge.service installed + enabled"

section "Step 7: joggy-capture — USER service + linger"

CAPTURE_SERVICE_SRC="${JOGGY_DIR}/apps/edge/infra/joggy-capture.user.service"
USER_SYSTEMD_DIR="/home/pi/.config/systemd/user"
CAPTURE_SERVICE_DST="${USER_SYSTEMD_DIR}/joggy-capture.service"

if [[ ! -f "$CAPTURE_SERVICE_SRC" ]]; then
    error "Service file not found: ${CAPTURE_SERVICE_SRC}"
fi

mkdir -p "$USER_SYSTEMD_DIR"
cp "$CAPTURE_SERVICE_SRC" "$CAPTURE_SERVICE_DST"

# Enable linger so user session survives across reboots (needed for uaccess ACL)
sudo loginctl enable-linger pi
ok "loginctl linger enabled for pi"

systemctl --user daemon-reload
systemctl --user enable joggy-capture
ok "joggy-capture.service installed + enabled (user-level)"

section "Step 8: Configure .env"

# Check if .env already has real values
ENV_NEEDS_UPDATE=false

if [[ -f "$ENV_FILE" ]]; then
    if grep -q "REPLACE_ME\|your-vps\|example" "$ENV_FILE"; then
        ENV_NEEDS_UPDATE=true
        info ".env exists but has placeholder values — will update"
    else
        ok ".env already configured"
    fi
else
    ENV_NEEDS_UPDATE=true
    info "No .env found — will create from template"
fi

if $ENV_NEEDS_UPDATE; then
    echo ""
    echo -e "${YELLOW}Configure Pi connection to VPS:${NC}"
    echo ""

    read -rp "  INGEST_URL (e.g. https://your-vps.example/ingest/photos): " INGEST_URL
    while [[ -z "$INGEST_URL" || "$INGEST_URL" == *"example"* ]]; do
        echo "  Please enter a real INGEST_URL"
        read -rp "  INGEST_URL: " INGEST_URL
    done

    read -rp "  EVENT_TOKEN (evt_xxxxx — generate from dashboard): " EVENT_TOKEN
    while [[ -z "$EVENT_TOKEN" || "${EVENT_TOKEN:0:4}" != "evt_" ]]; do
        echo "  TOKEN must start with evt_"
        read -rp "  EVENT_TOKEN: " EVENT_TOKEN
    done

    read -rp "  DEVICE_ID (e.g. pi-001) [pi-001]: " DEVICE_ID
    DEVICE_ID="${DEVICE_ID:-pi-001}"

    cat > "$ENV_FILE" << EOF
# Joggy-PicX Edge — generated by setup_pi.sh $(date '+%Y-%m-%d %H:%M:%S')
INGEST_URL=${INGEST_URL}
EVENT_TOKEN=${EVENT_TOKEN}
DEVICE_ID=${DEVICE_ID}
INBOX_DIR=/home/pi/photos/inbox
UPLOADED_DIR=/home/pi/photos/uploaded
FAILED_DIR=/home/pi/photos/failed
LOG_LEVEL=INFO
EOF
    ok ".env written to ${ENV_FILE}"
fi

section "Step 9: Start services"

# Start edge (system service)
sudo systemctl restart joggy-edge
sleep 3
if systemctl is-active --quiet joggy-edge; then
    ok "joggy-edge is running"
else
    warn "joggy-edge failed to start — check: journalctl -u joggy-edge -n 20"
fi

# Start capture (user service)
systemctl --user restart joggy-capture
sleep 8
if systemctl --user is-active --quiet joggy-capture; then
    ok "joggy-capture is running"
    info "Tip: if camera is not connected, service will retry every 10s after connecting"
else
    warn "joggy-capture failed to start — check: journalctl --user -u joggy-capture -n 20"
fi

section "Step 10: Smoke test"

echo ""
info "Testing VPS connectivity ..."

# Extract base URL from INGEST_URL
if [[ -f "$ENV_FILE" ]]; then
    INGEST_URL_VAL=$(grep '^INGEST_URL=' "$ENV_FILE" | cut -d= -f2-)
    # Derive health endpoint: replace /ingest/photos with /healthz
    HEALTH_URL=$(echo "$INGEST_URL_VAL" | sed 's|/ingest/photos.*|/healthz|')
    HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$HEALTH_URL" 2>/dev/null || echo "000")
    if [[ "$HTTP_CODE" == "200" ]]; then
        ok "VPS /healthz → HTTP 200 ✅"
    else
        warn "VPS /healthz → HTTP ${HTTP_CODE} (check VPS is running + URL is correct)"
    fi
fi

echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  Joggy-PicX Pi setup complete! 🎉${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "  Services installed:"
echo "    • joggy-edge    — system service (auto-starts at boot)"
echo "    • joggy-capture — user service   (auto-starts via linger)"
echo ""
echo "  Verify manually:"
echo "    systemctl status joggy-edge"
echo "    systemctl --user status joggy-capture"
echo "    journalctl -u joggy-edge -f"
echo "    journalctl --user -u joggy-capture -f"
echo ""
echo "  To rotate EVENT_TOKEN:"
echo "    sed -i 's|EVENT_TOKEN=.*|EVENT_TOKEN=evt_NEWTOKEN|' ${ENV_FILE}"
echo "    sudo systemctl restart joggy-edge"
echo ""
echo "  Connect Canon EOS RP via USB-C → press shutter → photo appears in dashboard"
echo ""
