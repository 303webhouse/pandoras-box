#!/bin/bash
# UW Integration Deployment Script for VPS
# Run this on root@5.78.134.70

set -e  # Exit on any error

echo "=== UW Integration Deployment ==="
echo "Starting deployment at $(date)"

# 1. Backup current .env
echo "[1/7] Backing up .env..."
if [ -f /opt/pivot/.env ]; then
    cp /opt/pivot/.env /opt/pivot/.env.backup.$(date +%Y%m%d_%H%M%S)
    echo "✓ Backup created"
else
    echo "⚠ No existing .env file found"
fi

# 2. Add UW environment variables
echo "[2/7] Adding UW environment variables..."
ENV_FILE="/opt/pivot/.env"

# Check if variables already exist
if grep -q "UW_FLOW_CHANNEL_ID" "$ENV_FILE" 2>/dev/null; then
    echo "⚠ UW_FLOW_CHANNEL_ID already exists, updating..."
    sed -i 's/^UW_FLOW_CHANNEL_ID=.*/UW_FLOW_CHANNEL_ID=1470543470820196493/' "$ENV_FILE"
else
    echo "UW_FLOW_CHANNEL_ID=1470543470820196493" >> "$ENV_FILE"
fi

if grep -q "UW_TICKER_CHANNEL_ID" "$ENV_FILE" 2>/dev/null; then
    echo "⚠ UW_TICKER_CHANNEL_ID already exists, updating..."
    sed -i 's/^UW_TICKER_CHANNEL_ID=.*/UW_TICKER_CHANNEL_ID=1470543542278426788/' "$ENV_FILE"
else
    echo "UW_TICKER_CHANNEL_ID=1470543542278426788" >> "$ENV_FILE"
fi

if grep -q "UW_BOT_USER_ID" "$ENV_FILE" 2>/dev/null; then
    echo "⚠ UW_BOT_USER_ID already exists, updating..."
    sed -i 's/^UW_BOT_USER_ID=.*/UW_BOT_USER_ID=1100705854271008798/' "$ENV_FILE"
else
    echo "UW_BOT_USER_ID=1100705854271008798" >> "$ENV_FILE"
fi

echo "✓ UW environment variables added"

# 3. Check for PIVOT_API_KEY
echo "[3/7] Checking for PIVOT_API_KEY..."
if grep -q "^PIVOT_API_KEY=" "$ENV_FILE" 2>/dev/null; then
    echo "✓ PIVOT_API_KEY exists"
else
    echo "❌ PIVOT_API_KEY is MISSING!"
    echo "Please add PIVOT_API_KEY to $ENV_FILE before continuing"
    echo "Contact Nick for the value"
    exit 1
fi

# 4. Pull latest code
echo "[4/7] Pulling latest code..."
cd /opt/pivot

if [ -d ".git" ]; then
    echo "Git repository detected, pulling latest changes..."
    git fetch origin
    git pull origin main || git pull origin master || {
        echo "⚠ Git pull failed, trying current branch..."
        git pull
    }
    echo "✓ Code updated"
else
    echo "❌ Not a git repository!"
    echo "Please confirm with Nick how code gets deployed to VPS"
    exit 1
fi

# 5. Install dependencies
echo "[5/7] Installing Python dependencies..."
if [ -f "requirements.txt" ]; then
    /opt/pivot/venv/bin/pip install -r requirements.txt --quiet
    echo "✓ Dependencies installed"
else
    echo "⚠ No requirements.txt found, skipping..."
fi

# 6. Restart the bot
echo "[6/7] Restarting pivot-bot service..."
systemctl restart pivot-bot
sleep 3

# Check status
systemctl status pivot-bot --no-pager -l

echo ""
echo "[7/7] Checking recent logs..."
journalctl -u pivot-bot --since "1 minute ago" --no-pager | tail -30

echo ""
echo "=== Deployment Complete ==="
echo "Please verify:"
echo "1. Check logs for UW channel discovery (#uw-live-flow, #uw-ticker-updates)"
echo "2. Test UW endpoints at https://pandoras-box-production.up.railway.app/api/uw/discovery"
echo "3. Try UW commands in Discord if available"
