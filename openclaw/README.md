# OpenClaw VPS Scripts

Scripts and config for the OpenClaw agent running on the Hetzner VPS (`188.245.250.2`).

**VPS paths:**
- Scripts: `/opt/openclaw/workspace/scripts/`
- Cron config: `/home/openclaw/.openclaw/cron/jobs.json`
- State data: `/opt/openclaw/workspace/data/`

## Deploy

```bash
ssh root@188.245.250.2

# Sync scripts
rsync -av pandoras-box/openclaw/scripts/ /opt/openclaw/workspace/scripts/

# Update cron jobs
cp pandoras-box/openclaw/cron/jobs.json /home/openclaw/.openclaw/cron/jobs.json

# Restart OpenClaw
systemctl restart openclaw

# Verify IBKR pollers
python3 /opt/openclaw/workspace/scripts/ibkr_poller.py --dry-run
python3 /opt/openclaw/workspace/scripts/ibkr_quotes.py --dry-run
```

## Files

| File | Purpose | Schedule |
|------|---------|----------|
| `scripts/ibkr_poller.py` | Poll IBKR positions + balances → portfolio API | `*/5 14-21 * * 1-5` |
| `scripts/ibkr_quotes.py` | Fetch IBKR option market data quotes | `*/1 14-21 * * 1-5` |
| `scripts/committee_interaction_handler.py` | Discord button handlers for TAKE/PASS/LATER | Event-driven |
| `cron/jobs.json` | OpenClaw cron schedule | — |

## DST Note (March 9, 2026)

When DST starts, market hours shift from `14-21 UTC` to `13-20 UTC`.
Update the `ibkr-position-poller` and `ibkr-quotes-poller` cron schedules in `jobs.json`
and redeploy.
