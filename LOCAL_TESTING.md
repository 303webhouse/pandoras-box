# 🧪 Local Testing Guide

Follow these steps to get Pandora's Box running locally with test data.

---

## Step 1: Install Python Dependencies

Open Command Prompt in `C:\trading-hub\backend\` (or wherever you extracted the files):

```bash
pip install -r requirements.txt --break-system-packages
```

**What this installs:**
- FastAPI (web server)
- Uvicorn (ASGI server)
- Redis client
- PostgreSQL client
- WebSocket support
- Everything else needed

**Expected time:** 2-3 minutes

---

## Step 2: Set Up Databases (Simplified for Testing)

For local testing, you have two options:

### Option A: Use Free Cloud Databases (Easiest)

**Redis via Upstash (30 seconds setup):**
1. Go to https://console.upstash.com/redis
2. Click "Create Database"
3. Name it "pandoras-box-test"
4. Copy the connection details

**PostgreSQL via Supabase (1 minute setup):**
1. Go to https://supabase.com/dashboard
2. Click "New Project"
3. Name it "pandoras-box-test"
4. Wait for it to initialize
5. Go to Settings → Database → Connection String
6. Copy the URI

### Option B: Install Locally (More Setup)

**Redis:**
```bash
# Windows: Use WSL or download from https://github.com/microsoftarchive/redis/releases
# OR use Docker:
docker run -d -p 6379:6379 redis:alpine
```

**PostgreSQL:**
```bash
# Download from https://www.postgresql.org/download/windows/
# OR use Docker:
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15
```

---

## Step 3: Configure Environment

1. Go to `C:\trading-hub\config\`
2. Copy `.env.example` to `.env`
3. Edit `.env`:

**If using cloud databases (Option A):**
```env
# Redis (from Upstash)
REDIS_HOST=grizzly-bear-12345.upstash.io
REDIS_PORT=6379

# PostgreSQL (from Supabase)
DB_HOST=db.abcdefghijk.supabase.co
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your-supabase-password
```

**If using local databases (Option B):**
```env
REDIS_HOST=localhost
REDIS_PORT=6379

DB_HOST=localhost
DB_PORT=5432
DB_NAME=pandoras_box
DB_USER=postgres
DB_PASSWORD=postgres
```

Save and close.

---

## Step 4: Initialize Database

Open Command Prompt in `C:\trading-hub\backend\`:

```bash
python -c "from database.postgres_client import init_database; import asyncio; asyncio.run(init_database())"
```

**What this does:**
- Creates `signals` table
- Creates `positions` table
- Creates `tick_history` table
- Creates `bias_history` table

**Expected output:**
```
✅ Database schema initialized
```

If you get an error, double-check your `.env` credentials.

---

## Step 5: Start Backend

In Command Prompt (`C:\trading-hub\backend\`):

```bash
python main.py
```

**Expected output:**
```
🚀 Pandora's Box backend starting...
✅ Database connections established
✅ Pandora's Box is live
INFO:     Uvicorn running on http://0.0.0.0:8000
```

**Leave this terminal window open.** Backend is now running.

---

## Step 6: Start Frontend

Open a **NEW** Command Prompt window in `C:\trading-hub\frontend\`:

```bash
python -m http.server 3000
```

**Expected output:**
```
Serving HTTP on 0.0.0.0 port 3000 (http://0.0.0.0:3000/) ...
```

**Leave this terminal window open too.**

---

## Step 7: Open Dashboard

Open your web browser and go to:

```
http://localhost:3000
```

**What you should see:**
- Dark teal dashboard loads
- "Live" connection status (green dot)
- Bias indicators show "Loading..."
- Signal columns are empty

**This is normal!** No data yet.

---

## Step 8: Populate Test Data

Open a **THIRD** Command Prompt window in `C:\trading-hub\backend\`:

```bash
python test_signals.py
```

**You'll see a menu:**
```
Choose an option:
1. Send all test signals (populate dashboard)
2. Send one random signal (test refresh)
3. Set test bias data
4. Do everything (signals + bias)

Enter choice (1-4):
```

**Type `4` and press Enter** (this does everything).

**Expected output:**
```
✅ Daily bias set: TORO_MINOR (Wide TICK range)
✅ Weekly bias set: TORO_MAJOR (Strong breadth)

📊 Pandora's Box - Test Signal Generator
============================================================
Sending 11 test signals to backend...

✅ AAPL LONG - APIS_CALL (27.3ms)
✅ MSFT LONG - APIS_CALL (15.8ms)
✅ TSLA SHORT - KODIAK_CALL (18.2ms)
✅ NVDA SHORT - KODIAK_CALL (16.5ms)
✅ GOOGL LONG - BULLISH_TRADE (14.9ms)
...
============================================================
✅ Test signals sent! Check your dashboard.
============================================================
```

---

## Step 9: Watch the Magic Happen

**Go back to your browser (http://localhost:3000)**

You should now see:

✅ **Bias Indicators Updated:**
- Daily Bias: TORO MINOR (green)
- Weekly Bias: TORO MAJOR (green)

✅ **Equity Column Populated:**
- ~8 signals showing
- Mix of APIS CALL, KODIAK CALL, BULLISH TRADE, BEAR CALL
- Each with Entry/Stop/Target prices

✅ **Crypto Column Populated:**
- BTC, ETH, SOL signals

**Try Interacting:**
- Click **✕ Dismiss** on a signal → it disappears
- Click **✓ Select** on a signal → moves to "Open Positions" section
- Click **↻ Refresh** → re-queries backend

---

## Step 10: Test Multi-Device Sync

**Open the dashboard on another device:**

1. **On your laptop:** Open http://localhost:3000
2. **On your phone:** 
   - Connect phone to same WiFi
   - Find your computer's local IP (run `ipconfig` in Command Prompt, look for IPv4)
   - Open http://YOUR-IP:3000 on phone

**Now dismiss or select a signal on one device** → Watch it update on all devices instantly via WebSocket!

---

## Troubleshooting

### "Module 'redis' has no attribute 'asyncio'"
Your Redis package is outdated. Run:
```bash
pip install redis[hiredis]==5.0.1 --break-system-packages --force-reinstall
```

### "Connection refused" to Redis/PostgreSQL
- Check `.env` credentials
- Verify databases are running (cloud or local)
- Test connection manually

### Backend crashes on startup
- Check all dependencies installed: `pip list | findstr fastapi`
- Look at error message - usually missing package or wrong `.env` value

### No signals appear after running test script
- Check backend terminal for errors
- Verify backend is running on port 8000
- Try running test script again

### WebSocket shows "Reconnecting..."
- Backend crashed or not started
- Check terminal running `main.py` for errors
- Restart backend

---

## What To Do Next

**If everything works:**
1. ✅ Test selecting/dismissing signals
2. ✅ Test refresh button
3. ✅ Test timeframe selector (Daily/Weekly/Monthly)
4. ✅ Test on multiple devices
5. ✅ Check Open Positions section

**When ready for production:**
1. Deploy backend to Railway
2. Deploy frontend to Vercel
3. Configure TradingView webhooks with production URL
4. Start receiving real trading signals!

---

## Running It Again Later

**Every time you want to use Pandora's Box:**

1. Open two Command Prompts
2. Terminal 1: `cd C:\trading-hub\backend` → `python main.py`
3. Terminal 2: `cd C:\trading-hub\frontend` → `python -m http.server 3000`
4. Open browser to http://localhost:3000

**OR just double-click `start.bat`** (does all of this automatically)

---

**You're ready to test! Start with Step 1.**
