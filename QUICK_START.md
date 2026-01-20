# 🚀 Quick Start Guide - Pandora's Box

## You've Downloaded the Project. Now What?

### Step 1: Extract the Files
1. Locate `trading-hub` folder in your downloads
2. Copy it to `C:\trading-hub` (or wherever you want)
3. Open that folder in File Explorer

---

### Step 2: Install Python (If You Haven't)
1. Go to https://www.python.org/downloads/
2. Download Python 3.10 or newer
3. **IMPORTANT**: Check "Add Python to PATH" during installation
4. Verify: Open Command Prompt and type `python --version`

---

### Step 3: Install Backend Dependencies
```bash
cd C:\trading-hub\backend
pip install -r requirements.txt --break-system-packages
```

This installs FastAPI, Redis, PostgreSQL drivers, etc.

---

### Step 4: Set Up Databases

**Option A: Use Free Cloud Databases (Recommended)**

**Redis (via Upstash)**:
1. Go to https://upstash.com
2. Create free account
3. Create Redis database
4. Copy connection details

**PostgreSQL (via Supabase)**:
1. Go to https://supabase.com
2. Create free account
3. Create new project
4. Copy database URL from project settings

**Option B: Install Locally**
- Redis: https://redis.io/download
- PostgreSQL: https://www.postgresql.org/download/

---

### Step 5: Configure Environment
1. Go to `C:\trading-hub\config\`
2. Copy `.env.example` → `.env`
3. Edit `.env` with your database credentials:

```env
REDIS_HOST=your-redis-host.upstash.io
REDIS_PORT=6379
DB_HOST=your-project.supabase.co
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your-password
```

---

### Step 6: Initialize Database
Open Command Prompt in `C:\trading-hub\backend\` and run:

```bash
python -c "from database.postgres_client import init_database; import asyncio; asyncio.run(init_database())"
```

This creates the tables for signals, positions, TICK history, etc.

---

### Step 7: Start the System

**Easy Way** (Windows):
1. Double-click `start.bat`
2. Two command windows open (backend + frontend)
3. Browser opens to http://localhost:3000

**Manual Way**:
```bash
# Terminal 1 - Backend
cd C:\trading-hub\backend
python main.py

# Terminal 2 - Frontend
cd C:\trading-hub\frontend
python -m http.server 3000
```

---

### Step 8: Test It Works
1. Dashboard should load at http://localhost:3000
2. Check connection status in header (should say "Live")
3. Bias indicators will show "Loading..." until you add TICK data

---

### Step 9: Configure TradingView Webhooks

**In TradingView**:
1. Create alert for your strategy
2. Set alert to "Webhook URL"
3. **Local testing**: Use ngrok or similar to expose localhost:8000
   - Install ngrok: https://ngrok.com/download
   - Run: `ngrok http 8000`
   - Use ngrok URL: `https://your-id.ngrok.io/webhook/tradingview`
4. **Production**: Use your deployed backend URL

**Alert Message** (JSON):
```json
{
  "ticker": "{{ticker}}",
  "strategy": "Triple Line Trend Retracement",
  "direction": "LONG",
  "entry_price": {{close}},
  "stop_loss": {{low}},
  "target_1": {{high}},
  "adx": 32.5,
  "line_separation": 15.2,
  "timeframe": "DAILY"
}
```

Replace `adx` and `line_separation` with actual values from your indicators.

---

### Step 10: Deploy to Cloud (Optional)

**Backend** (Railway):
1. Push code to GitHub
2. Go to https://railway.app
3. Connect repo
4. Select `backend/` as root directory
5. Add environment variables
6. Deploy

**Frontend** (Vercel):
1. Go to https://vercel.com
2. Import repo
3. Set build directory to `frontend/`
4. Deploy

**Update TradingView webhooks** to use your production backend URL.

---

## Troubleshooting

### "Command 'python' not found"
- Python not installed or not in PATH
- Reinstall Python with "Add to PATH" checked

### "Connection refused" in dashboard
- Backend not running
- Check if port 8000 is already in use
- Try running backend manually to see error messages

### "Database connection failed"
- Check credentials in `.env`
- Verify Redis/PostgreSQL are accessible
- Test connection manually

### No signals appearing
- TradingView webhook not configured
- Check backend logs for incoming webhooks
- Verify webhook URL is correct

### WebSocket won't connect
- Firewall blocking port 8000
- CORS issue (check browser console)
- Backend crashed (check terminal)

---

## Next Actions

1. ✅ **Get it running locally** (Steps 1-7)
2. ✅ **Test with manual webhook** (use Postman or curl)
3. ✅ **Connect TradingView** (Step 9)
4. ✅ **Install PWA on phone** (open dashboard in mobile browser → Add to Home Screen)
5. ✅ **Deploy to production** (Step 10)

---

## Support

- **Documentation**: Read `README.md` and `PROJECT_SUMMARY.md`
- **Code comments**: Every file has inline explanations
- **Architecture docs**: Check `docs/architecture/`

---

**You're ready to go. Start with Step 1!**
