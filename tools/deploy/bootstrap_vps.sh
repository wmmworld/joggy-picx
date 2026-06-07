#!/usr/bin/env bash
# Joggy-PicX VPS bootstrap — Hetzner CPX11 / Ubuntu 24.04 LTS
# Author: Claude (Tech Lead) — Phase 5 production deploy, 2026-06-06
#
# Idempotent: safe to re-run. Each step is a no-op if already done.
#
# Usage (as root, once SSH is set up):
#   curl -fsSL https://raw.githubusercontent.com/wmmworld/joggy-picx/master/tools/deploy/bootstrap_vps.sh | bash
# Or with local checkout:
#   sudo bash tools/deploy/bootstrap_vps.sh
#
# What this does:
#   1. Apt update + base packages
#   2. Create `joggy` user with sudo + docker group
#   3. Install Docker Engine + Compose plugin
#   4. ufw firewall: 22, 80, 443 only
#   5. fail2ban (default jail for sshd)
#   6. Install certbot
#   7. Print next steps (clone repo / .env / start services)

set -euo pipefail

log() { echo -e "\033[1;36m[bootstrap]\033[0m $*"; }
warn() { echo -e "\033[1;33m[warn]\033[0m $*"; }

if [[ $EUID -ne 0 ]]; then
  echo "This script must be run as root (sudo bash $0)" >&2
  exit 1
fi

# ── 1. Base packages ─────────────────────────────────────────────────────────
log "Updating apt + installing base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq \
    ca-certificates curl gnupg git ufw fail2ban \
    python3-venv python3-pip \
    htop tmux jq

# ── 2. Create joggy user ─────────────────────────────────────────────────────
if id joggy >/dev/null 2>&1; then
  log "User 'joggy' already exists — skipping create"
else
  log "Creating 'joggy' user with sudo access"
  useradd --create-home --shell /bin/bash --groups sudo joggy
  # Disable password — SSH key only
  passwd -l joggy
  # Copy authorized_keys from root if present
  if [[ -f /root/.ssh/authorized_keys ]]; then
    mkdir -p /home/joggy/.ssh
    cp /root/.ssh/authorized_keys /home/joggy/.ssh/
    chmod 700 /home/joggy/.ssh
    chmod 600 /home/joggy/.ssh/authorized_keys
    chown -R joggy:joggy /home/joggy/.ssh
    log "Copied SSH keys from root → joggy"
  fi
fi

# Passwordless sudo for joggy (deploys without TTY)
echo "joggy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/joggy
chmod 440 /etc/sudoers.d/joggy

# ── 3. Docker ────────────────────────────────────────────────────────────────
if command -v docker >/dev/null 2>&1; then
  log "Docker already installed: $(docker --version)"
else
  log "Installing Docker Engine + Compose plugin"
  curl -fsSL https://get.docker.com | sh
fi
usermod -aG docker joggy

# ── 4. Firewall ──────────────────────────────────────────────────────────────
log "Configuring ufw (allow 22/tcp, 80/tcp, 443/tcp)"
ufw --force reset >/dev/null
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

# ── 5. fail2ban ──────────────────────────────────────────────────────────────
log "Enabling fail2ban (sshd jail)"
cat > /etc/fail2ban/jail.d/sshd-local.conf <<'EOF'
[sshd]
enabled = true
port    = ssh
maxretry = 5
findtime = 10m
bantime = 1h
EOF
systemctl enable --now fail2ban

# ── 6. Certbot ───────────────────────────────────────────────────────────────
if command -v certbot >/dev/null 2>&1; then
  log "certbot already installed"
else
  log "Installing certbot (snap-free apt version)"
  apt-get install -y -qq certbot
fi

# ── 7. Repo dir + opt path ───────────────────────────────────────────────────
mkdir -p /opt/joggy-picx
chown joggy:joggy /opt/joggy-picx

# ── 8. Disable root SSH login (after joggy is set up) ────────────────────────
if grep -qE '^PermitRootLogin\s+(yes|prohibit-password)' /etc/ssh/sshd_config; then
  warn "Disabling root SSH login — make sure 'joggy' SSH works first!"
  sed -i 's/^PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
  systemctl reload ssh
fi

# ── Done ─────────────────────────────────────────────────────────────────────
log "Bootstrap complete!"
cat <<'NEXT'

╔══════════════════════════════════════════════════════════════════════╗
║                       Next Steps                                       ║
╚══════════════════════════════════════════════════════════════════════╝

1. Log out and re-login as 'joggy':
       ssh joggy@<vps-ip>

2. Clone the repo:
       cd /opt/joggy-picx
       git clone https://github.com/wmmworld/joggy-picx.git .

3. Create production .env:
       cp infra/env.production.template .env.production
       chmod 600 .env.production
       nano .env.production   # fill in real values

4. Apply Alembic migrations against Supabase:
       cd apps/backend
       uv sync --no-dev
       uv run alembic upgrade head
       cd /opt/joggy-picx

5. Build and start services:
       cd infra
       docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

6. SSL bootstrap (one-time):
       sudo certbot certonly --webroot -w /var/www/certbot -d YOUR_DOMAIN
       # Then activate HTTPS server block:
       mv infra/nginx/conf.d/ssl-joggy.conf.disabled infra/nginx/conf.d/ssl-joggy.conf
       sed -i 's/__YOUR_DOMAIN__/YOUR_DOMAIN/g' infra/nginx/conf.d/ssl-joggy.conf
       docker compose -f docker-compose.yml -f docker-compose.prod.yml restart nginx

7. Install PDPA retention cron:
       sudo cp infra/systemd/joggy-retention.* /etc/systemd/system/
       sudo systemctl daemon-reload
       sudo systemctl enable --now joggy-retention.timer

8. Verify everything:
       curl -fsS https://YOUR_DOMAIN/healthz
       docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
       sudo systemctl list-timers joggy-retention.timer

See docs/production-deploy.md for the full runbook.

NEXT
