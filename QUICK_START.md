# Pivot — Operations Quick Reference

**Last Updated:** February 19, 2026

This is a quick reference for operating and deploying Pivot. For full architecture details, read `CLAUDE.md`. For what's built vs planned, read `DEVELOPMENT_STATUS.md`.

---

## System Status Checks

```bash
# Backend API health (Railway)
curl https://pandoras-box-production.up.railway.app/health
# Expected: {"status":"healthy","postgres":"connected","redis":"ok","websocket_connections":N}

# Discord bot status (VPS)
ssh root@188.245.250.2 "systemctl status pivot-bot pivot-collector"

# Bot logs (live tail)
ssh root@188.245.250.2 "journalctl -u pivot-bot -f"

# Collector logs
ssh root@188.245.250.2 "journalctl -u pivot-collector -f"
```

---

## Deploy Backend (Railway)

Push to `main` → Railway auto-deploys. That's it.

```bash
git add -A && git commit -m "description" && git push origin main
```

Verify after deploy:
```bash
curl https://pandoras-box-production.up.railway.app/health
```

---

## Deploy Discord Bot (VPS)

Manual process — SSH in, pull, restart:

```bash
ssh root@188.245.250.2
cd /opt/pivot
git pull origin main
systemctl restart pivot-bot
journalctl -u pivot-bot -f   # ALWAYS verify startup
```

If collector changes were made too:
```bash
systemctl restart pivot-collector
journalctl -u pivot-collector -f
```

---

## Common Operations

### Restart bot after crash
```bash
ssh root@188.245.250.2 "systemctl restart pivot-bot"
```

### Check if Railway is eating credits
Railway dashboard → fabulous-essence project → Usage tab. Free tier gives $5/month.

### Force Railway redeploy (without code change)
Railway dashboard → pandoras-box service → Deployments → Redeploy latest.

### Check what's running on VPS
```bash
ssh root@188.245.250.2 "systemctl list-units | grep pivot"
```

### View recent bot errors
```bash
ssh root@188.245.250.2 "journalctl -u pivot-bot --since '1 hour ago' | grep -i error"
```

### Test a webhook locally
```bash
curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"ticker":"SPY","strategy":"test","direction":"LONG","timeframe":"15m"}'
```

---

## Environment Variable Safety

Railway uses `${{Postgres.*}}` template references that resolve to empty strings during build. Always use the `or` pattern:

```python
# CORRECT
DB_HOST = os.getenv("DB_HOST") or "localhost"
DB_PORT = int(os.getenv("DB_PORT") or 5432)

# WRONG — returns '' not None, causes int('') crash
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", 5432))
```

---

## Infrastructure Map

| What | Where | Access |
|------|-------|--------|
| Backend API | Railway (fabulous-essence) | `pandoras-box-production.up.railway.app` |
| PostgreSQL | Railway (same project) | Linked via `${{Postgres.*}}` |
| Redis | Upstash | `rediss://` URL in Railway env vars |
| Discord Bot | Hetzner VPS (PIVOT-EU) | `ssh root@188.245.250.2` |
| Data Collector | Same VPS | `pivot-collector.service` |
| Source Code | GitHub | `303webhouse/pandoras-box` |
| Frontend | Served from VPS | Port 3000 |

---

## Credential Locations

Credentials are NOT stored in the repo. They live in:

- **Railway env vars** — DB_*, DISCORD_*, API keys (Railway dashboard → pandoras-box service → Variables)
- **VPS .env file** — `/opt/pivot/.env` (Discord token, API keys, webhook URLs)
- **Nick's Claude.ai memory** — Contains all tokens/keys for reference in conversations
- **GitHub PAT** — Used for git operations on VPS, stored in git credential helper

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Bot offline | `ssh root@188.245.250.2 "systemctl restart pivot-bot"` |
| Railway deploy stuck | Railway dashboard → Redeploy or check build logs |
| Health returns `postgres: disconnected` | Check Railway Postgres service is running in fabulous-essence |
| Health returns `redis: error` | Verify Upstash Redis URL in Railway env vars starts with `rediss://` |
| Bot responds but no market data | Check `pivot-collector.service` is running |
| Duplicate bot responses | Ensure only ONE bot instance (VPS only, not Railway) |
| `int('')` crash on Railway | Missing `or` pattern in env var — see safety section above |
| Stale bias data | Check collector logs: `journalctl -u pivot-collector --since '1 hour ago'` |
