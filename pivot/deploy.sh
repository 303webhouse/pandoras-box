#!/bin/bash
# deploy.sh — Deploy Pivot agent to /opt/pivot on a Hetzner/Debian server.
#
# Run as root from the pandoras-box repo root:
#   bash pivot/deploy.sh
#
# On subsequent deploys (code updates only, .env already set):
#   bash pivot/deploy.sh --update

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PIVOT_DIR="$REPO_ROOT/pivot"
BRIDGE_DIR="$REPO_ROOT/backend/discord_bridge"
INSTALL_DIR="/opt/pivot"
PIVOT_USER="pivot"
PYTHON="${PYTHON:-python3}"
UPDATE_ONLY="${1:-}"

echo "=== Pivot Agent Deployment ==="
echo "Repo root:   $REPO_ROOT"
echo "Install dir: $INSTALL_DIR"
echo ""

# ── 1. System user ────────────────────────────────────────────────────────────
if ! id "$PIVOT_USER" &>/dev/null; then
    useradd -r -m -s /bin/bash "$PIVOT_USER"
    echo "[+] Created system user: $PIVOT_USER"
fi

# ── 2. Sync code ──────────────────────────────────────────────────────────────
mkdir -p "$INSTALL_DIR"

echo "[+] Syncing pivot package..."
rsync -a --delete \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='.env.example' \
    --exclude='venv' \
    "$PIVOT_DIR/" "$INSTALL_DIR/"

echo "[+] Syncing discord_bridge..."
rsync -a --delete \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    "$BRIDGE_DIR/" "$INSTALL_DIR/discord_bridge/"

chown -R "$PIVOT_USER:$PIVOT_USER" "$INSTALL_DIR"

# ── 3. Verify .env ────────────────────────────────────────────────────────────
if [ ! -f "$INSTALL_DIR/.env" ]; then
    if [ "$UPDATE_ONLY" = "--update" ]; then
        echo "ERROR: $INSTALL_DIR/.env not found. Cannot update without it."
        exit 1
    fi
    echo ""
    echo "ERROR: $INSTALL_DIR/.env not found."
    echo "Create it from the template then re-run:"
    echo ""
    echo "  cp $PIVOT_DIR/.env.example $INSTALL_DIR/.env"
    echo "  nano $INSTALL_DIR/.env"
    echo ""
    exit 1
fi
chmod 600 "$INSTALL_DIR/.env"
chown "$PIVOT_USER:$PIVOT_USER" "$INSTALL_DIR/.env"

# ── 4. Runtime directories ────────────────────────────────────────────────────
for d in logs state cache; do
    mkdir -p "$INSTALL_DIR/$d"
    chown "$PIVOT_USER:$PIVOT_USER" "$INSTALL_DIR/$d"
done

# ── 5. Python venv ────────────────────────────────────────────────────────────
if [ ! -f "$INSTALL_DIR/venv/bin/python" ]; then
    echo "[+] Creating virtual environment..."
    sudo -u "$PIVOT_USER" "$PYTHON" -m venv "$INSTALL_DIR/venv"
fi

echo "[+] Installing Python dependencies..."
sudo -u "$PIVOT_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet --upgrade pip
sudo -u "$PIVOT_USER" "$INSTALL_DIR/venv/bin/pip" install --quiet -r "$INSTALL_DIR/requirements.txt"

# ── 6. pivot-collector.service ────────────────────────────────────────────────
cat > /etc/systemd/system/pivot-collector.service << 'EOF'
[Unit]
Description=Pivot Trading Data Collector
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pivot
WorkingDirectory=/opt/pivot
ExecStart=/opt/pivot/venv/bin/python -m scheduler.cron_runner
Restart=always
RestartSec=10
EnvironmentFile=/opt/pivot/.env
Environment=PYTHONPATH=/opt/pivot

[Install]
WantedBy=multi-user.target
EOF

# ── 7. pivot-bot.service ──────────────────────────────────────────────────────
cat > /etc/systemd/system/pivot-bot.service << 'EOF'
[Unit]
Description=Pivot Discord Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pivot
WorkingDirectory=/opt/pivot
ExecStart=/opt/pivot/venv/bin/python /opt/pivot/bot.py
Restart=always
RestartSec=15
EnvironmentFile=/opt/pivot/.env
Environment=PYTHONPATH=/opt/pivot

[Install]
WantedBy=multi-user.target
EOF

# ── 8. Enable and restart ─────────────────────────────────────────────────────
systemctl daemon-reload
systemctl enable pivot-collector pivot-bot
systemctl restart pivot-collector
sleep 2
systemctl restart pivot-bot

echo ""
echo "=== Deployment complete ==="
echo ""
echo "  Collector:  systemctl status pivot-collector"
echo "  Bot:        systemctl status pivot-bot"
echo "  Logs:       journalctl -u pivot-collector -f"
echo "              journalctl -u pivot-bot -f"
echo "              tail -f $INSTALL_DIR/logs/pivot.log"
