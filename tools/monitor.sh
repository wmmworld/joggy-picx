#!/usr/bin/env bash
# =============================================================================
# Joggy-PicX — Pi field health check
# =============================================================================
# One-command "is everything OK?" snapshot for the Raspberry Pi running edge
# uploader + camera capture. Designed for ops in the field: read top to
# bottom, every ✅ green means the pipeline is healthy.
#
# Usage:
#   bash tools/monitor.sh           # show snapshot
#   bash tools/monitor.sh --watch   # refresh every 10s (Ctrl+C to stop)
# =============================================================================

set -u

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
DIM='\033[2m'
NC='\033[0m'

ok()    { echo -e "  ${GREEN}✓${NC} $*"; }
warn()  { echo -e "  ${YELLOW}!${NC} $*"; }
bad()   { echo -e "  ${RED}✗${NC} $*"; }
info()  { echo -e "  ${DIM}·${NC} $*"; }
title() { echo -e "\n${BLUE}── $* ──${NC}"; }


snapshot() {
    clear 2>/dev/null || true
    echo -e "${BLUE}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}║       Joggy-PicX — Pi field health check                 ║${NC}"
    echo -e "${BLUE}║       $(date '+%Y-%m-%d %H:%M:%S')  hostname=$(hostname)                  ║${NC}"
    echo -e "${BLUE}╚══════════════════════════════════════════════════════════╝${NC}"

    # ── Services ─────────────────────────────────────────────────────────────
    title "Services"

    edge_state=$(systemctl is-active joggy-edge 2>/dev/null || echo "missing")
    capture_state=$(systemctl --user is-active joggy-capture 2>/dev/null || echo "missing")

    [[ "$edge_state" == "active" ]] && ok "joggy-edge       active" || bad "joggy-edge       $edge_state"
    [[ "$capture_state" == "active" ]] && ok "joggy-capture    active" || bad "joggy-capture    $capture_state"

    # Show uptime if active
    if [[ "$edge_state" == "active" ]]; then
        edge_since=$(systemctl show joggy-edge --property=ActiveEnterTimestamp --value 2>/dev/null)
        [[ -n "$edge_since" ]] && info "edge running since: $edge_since"
    fi
    if [[ "$capture_state" == "active" ]]; then
        cap_since=$(systemctl --user show joggy-capture --property=ActiveEnterTimestamp --value 2>/dev/null)
        [[ -n "$cap_since" ]] && info "capture running since: $cap_since"
    fi

    # ── Camera (gphoto2) ─────────────────────────────────────────────────────
    title "Camera (Canon EOS RP via USB)"

    if lsusb 2>/dev/null | grep -qi canon; then
        canon_line=$(lsusb | grep -i canon)
        ok "Canon device enumerated"
        info "$canon_line"
    else
        bad "No Canon device on USB"
    fi

    # capture log: last "Waiting for events" or "Saving file"
    last_capture=$(journalctl --user -u joggy-capture --since "10 min ago" --no-pager 2>/dev/null \
        | grep -E "Waiting for events|Saving file|CAPTURECOMPLETE|ERROR|Permission denied" \
        | tail -1)
    if [[ -n "$last_capture" ]]; then
        info "last capture event: $last_capture"
    fi

    # ── Inbox / Uploaded counts ──────────────────────────────────────────────
    title "Photo flow"

    inbox_count=$(ls /home/pi/photos/inbox/ 2>/dev/null | grep -c '\.jpg$' || echo 0)
    uploaded_today=$(find /home/pi/photos/uploaded -type f -name '*.jpg' -newermt "$(date '+%Y-%m-%d')" 2>/dev/null | wc -l)
    failed_count=$(ls /home/pi/photos/failed/ 2>/dev/null | grep -c '\.jpg$' || echo 0)

    if [[ "$inbox_count" -gt 50 ]]; then
        warn "inbox: $inbox_count waiting (upload may be stuck?)"
    else
        info "inbox: $inbox_count waiting"
    fi
    info "uploaded today: $uploaded_today"
    if [[ "$failed_count" -gt 0 ]]; then
        warn "failed: $failed_count (check /home/pi/photos/failed/)"
    else
        info "failed: 0"
    fi

    # stuck marker check (edge daemon touches this if upload stuck for too long)
    if ls /tmp/joggy-edge-stuck* >/dev/null 2>&1; then
        bad "stuck marker present: $(ls /tmp/joggy-edge-stuck* 2>/dev/null)"
    fi

    # ── Recent uploads (last 5) ──────────────────────────────────────────────
    title "Recent uploads (last 5)"

    recent=$(journalctl -u joggy-edge --since "30 min ago" --no-pager 2>/dev/null \
        | grep "Uploaded" | tail -5)
    if [[ -n "$recent" ]]; then
        echo "$recent" | while read -r line; do
            ts=$(echo "$line" | awk '{print $1, $2, $3}')
            fname=$(echo "$line" | grep -oE 'Uploaded [^ ]+' | head -1)
            info "$ts  $fname"
        done
    else
        info "(no uploads in last 30 min)"
    fi

    # ── System resources ─────────────────────────────────────────────────────
    title "System"

    mem=$(free -h | awk '/^Mem/{print $3"/"$2}')
    info "memory: $mem"

    temp_raw=$(cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null)
    if [[ -n "$temp_raw" ]]; then
        temp=$(awk "BEGIN{printf \"%.1f\", $temp_raw/1000}")
        if (( $(echo "$temp > 70" | bc -l 2>/dev/null || echo 0) )); then
            warn "CPU temp: ${temp}°C (hot — check ventilation)"
        else
            info "CPU temp: ${temp}°C"
        fi
    fi

    disk=$(df -h /home/pi/photos 2>/dev/null | awk 'NR==2 {print $5" used ("$4" free)"}')
    [[ -n "$disk" ]] && info "disk: $disk"

    # network — can we reach VPS?
    if [[ -f /home/pi/joggy/.env ]]; then
        ingest_url=$(grep '^INGEST_URL=' /home/pi/joggy/.env 2>/dev/null | cut -d= -f2-)
        if [[ -n "$ingest_url" ]]; then
            health_url=$(echo "$ingest_url" | sed 's|/ingest/photos.*|/healthz|')
            http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$health_url" 2>/dev/null || echo "000")
            if [[ "$http_code" == "200" ]]; then
                ok "VPS reachable (HTTP 200 on /healthz)"
            else
                bad "VPS unreachable (HTTP $http_code on $health_url)"
            fi
        fi
    fi

    # ── Network ──────────────────────────────────────────────────────────────
    title "Network"

    ip=$(hostname -I | awk '{print $1}')
    info "Pi IP: $ip"

    if command -v nmcli >/dev/null 2>&1; then
        ssid=$(nmcli -t -f active,ssid dev wifi 2>/dev/null | grep '^yes' | cut -d: -f2 | head -1)
        [[ -n "$ssid" ]] && info "WiFi: $ssid"
    fi

    echo ""
}


# ── Main ─────────────────────────────────────────────────────────────────────

if [[ "${1:-}" == "--watch" ]]; then
    trap 'echo; echo "Exiting monitor."; exit 0' INT
    while true; do
        snapshot
        echo -e "${DIM}(refresh in 10s — Ctrl+C to exit)${NC}"
        sleep 10
    done
else
    snapshot
fi
