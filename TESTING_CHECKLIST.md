# ✅ Local Testing Checklist

Print this out or keep it open while testing.

---

## Prerequisites (One-Time Setup)

- [ ] Python 3.10+ installed (`python --version`)
- [ ] Redis database ready (Upstash or local)
- [ ] PostgreSQL database ready (Supabase or local)
- [ ] `.env` file configured with database credentials
- [ ] Dependencies installed (`pip install -r requirements.txt --break-system-packages`)
- [ ] Database initialized (`python -c "from database.postgres_client import init_database; import asyncio; asyncio.run(init_database())"`)

---

## Every Time You Start

- [ ] Open Command Prompt #1 → `cd backend` → `python main.py`
  - Wait for: "✅ Pandora's Box is live"
  
- [ ] Open Command Prompt #2 → `cd frontend` → `python -m http.server 3000`
  - Wait for: "Serving HTTP on 0.0.0.0 port 3000"
  
- [ ] Open browser → http://localhost:3000
  - Dashboard loads
  - Connection status shows "Live" (green dot)

---

## Populate Test Data (First Time)

- [ ] Open Command Prompt #3 → `cd backend` → `python test_signals.py`
- [ ] Choose option `4` (Do everything)
- [ ] Verify in browser:
  - Bias indicators show TORO MAJOR/MINOR (green)
  - Equity column shows ~8 signals
  - Crypto column shows BTC/ETH/SOL signals

---

## Test Functionality

### Signal Management
- [ ] Click **✕ Dismiss** on a signal → disappears from list
- [ ] Click **✓ Select** on a signal → moves to "Open Positions"
- [ ] Click **↻ Refresh** → re-queries backend

### Timeframe Selector
- [ ] Change from Weekly → Daily → Monthly
- [ ] Signals update (if you have different timeframe data)

### Tabs
- [ ] Click "Watchlist" tab → shows watchlist signals
- [ ] Click "Market-Wide" tab → shows all market signals

### Multi-Device Sync
- [ ] Open http://localhost:3000 on another device
- [ ] Dismiss signal on Device A → disappears on Device B instantly
- [ ] Select signal on Device B → appears in positions on Device A

---

## What Success Looks Like

✅ **Visual:**
- Dark teal background
- Lime green for bullish signals
- Orange for bearish signals
- Clean, readable layout

✅ **Performance:**
- Signals appear instantly when test script runs
- No lag when clicking buttons
- WebSocket reconnects if backend restarts

✅ **Functionality:**
- All buttons work
- Signals move between sections correctly
- Open positions display properly
- Connection status accurate

---

## Common Issues & Fixes

### "Module not found" errors
```bash
pip install -r requirements.txt --break-system-packages --force-reinstall
```

### Backend won't start
- Check `.env` has correct database credentials
- Verify Redis/PostgreSQL are accessible
- Look at error message in terminal

### No test signals appear
- Verify backend is running (check terminal #1)
- Run test script again: `python test_signals.py` → option 1
- Check browser console (F12) for errors

### WebSocket won't connect
- Backend must be running first
- Check firewall isn't blocking port 8000
- Restart browser

---

## When You're Done Testing

- [ ] Press any key in Command Prompt #1 (backend stops)
- [ ] Press Ctrl+C in Command Prompt #2 (frontend stops)
- [ ] Close browser tabs

**OR if you used `start.bat`:**
- [ ] Go back to the batch file window
- [ ] Press any key → stops everything automatically

---

## Next Steps After Successful Testing

- [ ] Read `PROJECT_SUMMARY.md` to understand architecture
- [ ] Review code comments to see how it works
- [ ] Check `TODO.md` for aesthetic improvements
- [ ] Deploy to production (see `QUICK_START.md` Step 10)
- [ ] Configure real TradingView webhooks
- [ ] Start receiving live trading signals!

---

**Everything working? You're ready for production deployment!**
