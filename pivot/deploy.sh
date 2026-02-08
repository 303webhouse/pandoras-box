#!/bin/bash
# deploy.sh — Run on the Hetzner VPS as root or with sudo

set -e

echo "=== Pivot Agent Deployment ==="

# Create user
useradd -m -s /bin/bash pivot 2>/dev/null || true

# Create directory
mkdir -p /opt/pivot
chown pivot:pivot /opt/pivot

echo "Copy the Pivot code into /opt/pivot before continuing."
echo "Press Enter to continue..."
read

# Python environment
sudo -u pivot bash -c '
cd /opt/pivot
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
'

# Verify .env exists
if [ ! -f /opt/pivot/.env ]; then
    echo "ERROR: /opt/pivot/.env not found!"
    echo "Create it using the template in pivot/.env.example"
    exit 1
fi

# Create log directory
mkdir -p /opt/pivot/logs
chown pivot:pivot /opt/pivot/logs

# Install systemd service
cat > /etc/systemd/system/pivot-collector.service << 'EOF'
[Unit]
Description=Pivot Trading Data Collector
After=network.target

[Service]
Type=simple
User=pivot
WorkingDirectory=/opt/pivot
ExecStart=/opt/pivot/venv/bin/python -m scheduler.cron_runner
Restart=always
RestartSec=10
Environment=PYTHONPATH=/opt/pivot

[Install]
WantedBy=multi-user.target
EOF

# Enable and start
systemctl daemon-reload
systemctl enable pivot-collector
systemctl start pivot-collector

echo "=== Deployment complete ==="
echo "Check status:  systemctl status pivot-collector"
echo "Check logs:    journalctl -u pivot-collector -f"
