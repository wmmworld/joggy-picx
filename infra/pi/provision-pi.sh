#!/usr/bin/env bash
# Codex: skeleton provisioning script สำหรับ Raspberry Pi 5 ตาม docs/canon-ftp-test.md
set -euo pipefail

# Codex: helper สำหรับ log ที่อ่านง่าย
log() {
  printf '[pi-provision] %s\n' "$1"
}

# Codex: bootstrap dependencies สำหรับ FTP ingest + hotspot + Python runtime
install_base_packages() {
  log "Updating apt packages"
  sudo apt update
  sudo apt upgrade -y

  log "Installing base packages"
  sudo apt install -y \
    vsftpd \
    hostapd \
    dnsmasq \
    python3-pip \
    python3-venv \
    watchdog \
    inotify-tools \
    curl
}

# Codex: เตรียม FTP user/folder สำหรับ Canon EOS RP upload
setup_ftp_user() {
  local ftp_user="${1:-canon}"
  local ftp_home="/srv/ftp/${ftp_user}"

  log "Creating ftp user: ${ftp_user}"
  if ! id -u "${ftp_user}" >/dev/null 2>&1; then
    sudo useradd -m -d "${ftp_home}" -s /usr/sbin/nologin "${ftp_user}"
  fi

  sudo mkdir -p "${ftp_home}/inbox"
  sudo chown -R "${ftp_user}:${ftp_user}" "${ftp_home}"
  log "Remember to set password manually: sudo passwd ${ftp_user}"
}

# Codex: วาง placeholder config templates เพื่อให้ทีมเติมค่าจริงก่อนใช้งานสนาม
write_config_templates() {
  log "Writing config templates"
  sudo mkdir -p /etc/joggy-picx
  sudo tee /etc/joggy-picx/README.txt >/dev/null <<'EOF'
This directory stores Joggy-PicX Pi provisioning templates.
Review docs/canon-ftp-test.md before enabling services in production.
EOF
}

main() {
  log "Start Pi provisioning skeleton"
  install_base_packages
  setup_ftp_user "${1:-canon}"
  write_config_templates
  log "Done. Next: apply real vsftpd/hostapd configs from docs/canon-ftp-test.md"
}

main "$@"
