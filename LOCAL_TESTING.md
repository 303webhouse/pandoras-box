# Pivot — Local Development Guide

**Last Updated:** February 19, 2026

How to run parts of Pivot locally for development and testing. The live system runs on Railway (backend) + VPS (bot), but you can run the backend locally for faster iteration.

---

## Prerequisites

- Python 3.12+
- Git access to `303webhouse/pandoras-box`
- `.env` file with required credentials (see `pivot/.env.example`)

---

## Running Backend Locally

The backend API can run locally and connect to the Railway PostgreSQL and Upstash Redis.

```bash
git clone https://github.com/303webhouse/pandoras-box.git
cd pandoras-box/backend
pip install -r ../requirements.txt --break-system-packages
```

Create a `.env` in the `config/` directory with the Railway database credentials (find these in Railway dashboard → fabulous-essence → pandoras-box service → Variables):

```env
DB_HOST=<railway-postgres-host>
DB_PORT=<railway-postgres-port>
DB_NAME=railway
DB_USER=postgres
DB_PASSWORD=<railway-postgres-password>
REDIS_URL=rediss://<upstash-redis-url>
```

**Important:** Use the `or` pattern if modifying any env var loading:
```python
# CORRECT
DB_HOST = os.getenv("DB_HOST") or "localhost"

# WRONG
DB_HOST = os.getenv("DB_HOST", "localhost")
```

Start the backend:
```bash
python main.py
# API runs on http://localhost:8000
```

Test it:
```bash
curl http://localhost:8000/health
```

---

## Running Frontend Locally

```bash
cd frontend
python -m http.server 3000
# Open http://localhost:3000
```

The frontend connects to the backend via WebSocket. Update the API URL in `frontend/app.js` if pointing at localhost instead of Railway.

---

## Testing Webhooks Locally

To receive TradingView webhooks locally, you'd need to expose port 8000 via a tunnel (ngrok, cloudflared, etc.). For most development, it's easier to:

1. Make changes locally
2. Push to `main` (triggers Railway deploy)
3. Test against the live Railway URL

```bash
# Test webhook format
curl -X POST http://localhost:8000/webhook/tradingview \
  -H "Content-Type: application/json" \
  -d '{"ticker":"SPY","strategy":"test","direction":"LONG","timeframe":"15m"}'
```

---

## Running the Discord Bot Locally

⚠️ **Only do this if the VPS bot is stopped first.** Two bot instances cause duplicate Discord gateway connections.

```bash
ssh root@188.245.250.2 "systemctl stop pivot-bot"  # Stop VPS bot first

cd pandoras-box
python run_discord_bot.py
```

When done, restart the VPS bot:
```bash
ssh root@188.245.250.2 "systemctl start pivot-bot"
```

---

## What NOT to Do Locally

- **Don't run the Discord bot while VPS bot is running** — duplicate gateway connections
- **Don't use `os.getenv("VAR", default)`** — use `os.getenv("VAR") or default` instead
- **Don't edit files directly on VPS** — always commit to git and `git pull` on VPS
- **Don't create a separate Postgres database** — use the Railway instance for consistency

---

## Development Workflow

The recommended workflow is:

1. **Discuss architecture** in Claude.ai (this is the planning layer)
2. **Write a markdown brief** describing exactly what to build
3. **Hand brief to Claude Code (Codex)** for implementation
4. **Test locally** if needed (backend only)
5. **Push to main** → Railway auto-deploys backend
6. **SSH to VPS** → `git pull && systemctl restart pivot-bot` for bot changes
7. **Verify** via health endpoint and Discord interaction
