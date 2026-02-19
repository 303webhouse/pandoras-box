# Pivot — Post-Deploy Verification Checklist

**Last Updated:** February 19, 2026

Run through this after any deployment to confirm everything is working.

---

## After Railway Deploy (Backend)

- [ ] Health check passes:
  ```bash
  curl https://pandoras-box-production.up.railway.app/health
  ```
- [ ] Response includes: `"status":"healthy"`, `"postgres":"connected"`, `"redis":"ok"`
- [ ] WebSocket connections count is ≥1 (bot should be connected)
- [ ] Check Railway dashboard for build errors (fabulous-essence → pandoras-box → Deployments)

---

## After VPS Deploy (Discord Bot)

- [ ] Service is running:
  ```bash
  ssh root@188.245.250.2 "systemctl status pivot-bot"
  ```
- [ ] No crash in recent logs:
  ```bash
  ssh root@188.245.250.2 "journalctl -u pivot-bot --since '5 minutes ago'"
  ```
- [ ] Bot responds in Discord #pivot-chat (send a test message)
- [ ] Collector is running (if collector changes were made):
  ```bash
  ssh root@188.245.250.2 "systemctl status pivot-collector"
  ```

---

## After Webhook Changes

- [ ] Test TradingView webhook format:
  ```bash
  curl -X POST https://pandoras-box-production.up.railway.app/webhook/tradingview \
    -H "Content-Type: application/json" \
    -d '{"ticker":"SPY","strategy":"test","direction":"LONG","timeframe":"15m"}'
  ```
- [ ] Response is 200 with signal ID
- [ ] Signal appears in Discord (if bot is connected)
- [ ] Signal appears in PostgreSQL signals table

---

## After Bot Personality/Prompt Changes

- [ ] Updated `pivot/llm/prompts.py` deployed to VPS
- [ ] Bot responds with updated behavior in #pivot-chat
- [ ] Playbook v2.1 references are intact (check system prompt includes risk rules)
- [ ] Bias challenge behavior works (test with a directionally biased question)

---

## After Factor/Collector Changes

- [ ] Collector service restarted:
  ```bash
  ssh root@188.245.250.2 "systemctl restart pivot-collector"
  ```
- [ ] Factor data appearing in Redis (check via bias endpoint)
- [ ] Factor history writing to PostgreSQL
- [ ] EOD brief reflects new/updated factors

---

## After Database Schema Changes

- [ ] Migration applied to Railway PostgreSQL
- [ ] Health endpoint still shows `postgres: connected`
- [ ] No errors in Railway deploy logs related to DB
- [ ] Existing data preserved (check row counts on critical tables)

---

## Weekly Sanity Checks

- [ ] Railway billing: free tier $5/month credit not exceeded
- [ ] VPS disk space: `ssh root@188.245.250.2 "df -h"`
- [ ] Bot uptime: `ssh root@188.245.250.2 "systemctl show pivot-bot --property=ActiveEnterTimestamp"`
- [ ] Stale factors: Check which factors haven't updated recently
- [ ] Signal accumulation: Are new signals being logged to PostgreSQL?
