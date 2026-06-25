# UW Integration VPS Deployment Instructions

## Quick Deploy (Automated)

```bash
# On your local machine, copy the script to VPS:
scp deploy_uw_integration.sh root@5.78.134.70:/tmp/

# SSH into VPS:
ssh root@5.78.134.70

# Run the deployment script:
chmod +x /tmp/deploy_uw_integration.sh
/tmp/deploy_uw_integration.sh
```

## Manual Deploy (Step-by-Step)

### 1. SSH into VPS
```bash
ssh root@5.78.134.70
```

### 2. Add UW Environment Variables
```bash
# Edit .env file
nano /opt/pivot/.env

# Add these three lines:
UW_FLOW_CHANNEL_ID=1470543470820196493
UW_TICKER_CHANNEL_ID=1470543542278426788
UW_BOT_USER_ID=1100705854271008798
```

### 3. Check for PIVOT_API_KEY
```bash
grep PIVOT_API_KEY /opt/pivot/.env
```
**If missing:** Contact Nick for the PIVOT_API_KEY value and add it to `.env`

### 4. Pull Latest Code
```bash
cd /opt/pivot

# Check if git repo
ls -la .git

# Pull latest code
git pull
```
**If not a git repo:** Ask Nick how code gets deployed (SCP, rsync, etc.)

### 5. Install Dependencies
```bash
/opt/pivot/venv/bin/pip install -r /opt/pivot/requirements.txt
```

### 6. Restart Bot Service
```bash
systemctl restart pivot-bot
sleep 3
systemctl status pivot-bot --no-pager
```

### 7. Verify Deployment

#### Check Logs for UW Channel Discovery
```bash
journalctl -u pivot-bot --since "1 minute ago" --no-pager | tail -50
```
Look for messages indicating:
- `#uw-live-flow` channel found
- `#uw-ticker-updates` channel found

#### Test UW API Endpoints
```bash
# From VPS or local machine:
curl https://pandoras-box-production.up.railway.app/api/uw/discovery
```

#### Test Discord Commands (if available)
In Discord, try UW-related commands that Codex may have added.

## Troubleshooting

### Bot Fails to Start
```bash
# Check detailed logs
journalctl -u pivot-bot --since "5 minutes ago" --no-pager

# Check service status
systemctl status pivot-bot -l
```

### UW Channels Not Found
- Verify the bot has access to the channels
- Check bot user ID matches: `1100705854271008798`
- Verify channel IDs in Discord

### Missing PIVOT_API_KEY
Contact Nick immediately - the bot cannot communicate with Railway API without this key.

## Environment Variables Summary

| Variable | Value | Purpose |
|----------|-------|---------|
| `UW_FLOW_CHANNEL_ID` | `1470543470820196493` | #uw-live-flow channel |
| `UW_TICKER_CHANNEL_ID` | `1470543542278426788` | #uw-ticker-updates channel |
| `UW_BOT_USER_ID` | `1100705854271008798` | UW bot user ID |
| `PIVOT_API_KEY` | *Ask Nick* | Railway API authentication |

## Post-Deployment Verification

1. ✅ Bot service running: `systemctl is-active pivot-bot`
2. ✅ UW channels discovered in logs
3. ✅ `/api/uw/discovery` endpoint responds
4. ✅ No errors in last 5 minutes of logs

---

**Deployment created by Claude Code on 2026-02-10**
