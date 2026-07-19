# Stable Market Board

A local trading dashboard for daily theme analysis, breadth tracking, and
relative strength scanning. Pulls daily OHLCV from Polygon, computes metrics
locally in DuckDB, serves a Bloomberg-style web dashboard at localhost:8000.

Built by Ryan Scott. Shared as-is with you, no support guarantees. If
something breaks, you're on your own to debug, but the code is straightforward.

## What you need before starting

1. **A Windows or Mac computer** with admin rights to install software
2. **Python 3.11 or newer** (instructions below if not installed)
3. **A Polygon.io account** with the Stocks Starter plan ($29/month) or higher.
   The free tier won't work, the rate limits will choke 5 years of history for
   280+ tickers. Polygon Starter has unlimited API calls and 5 years of history,
   which is what we need.
4. **About 30 minutes** for first-time setup

## Step-by-step setup

### Step 1: Install Python

**Windows:**
1. Go to https://www.python.org/downloads/
2. Click the "Download Python 3.x" button
3. Run the installer
4. **IMPORTANT: Check the box that says "Add python.exe to PATH"** before clicking Install
5. After install, open PowerShell and type `python --version`. You should see something like `Python 3.12.x`
6. If you get "python not recognized" you missed the PATH checkbox. Uninstall and reinstall, checking the box this time.

**Mac:**
1. Install via Homebrew if you have it: `brew install python@3.12`
2. Or download from https://www.python.org/downloads/
3. After install, open Terminal and type `python3 --version`, should show `Python 3.12.x`

### Step 2: Get your Polygon API key

1. Go to https://polygon.io and sign up
2. Subscribe to the Stocks Starter plan ($29/month). This is required.
3. In your Polygon dashboard, find your API key (Dashboard then Keys)
4. Copy it somewhere safe, it looks like a long random string

### Step 3: Extract this project

Extract this zip file to a folder. **Important: pick a path outside OneDrive.**
OneDrive sync can corrupt the local database file.

- Good location on Windows: `C:\Code\stable_market_board`
- Good location on Mac: `~/Code/stable_market_board`
- Bad locations: anywhere under OneDrive\Desktop, OneDrive\Documents, iCloud Drive

The folder should look like:
```
stable_market_board/
├── README.md (this file)
├── requirements.txt
├── install_check.py
├── run_dashboard.bat (Windows)
├── run_dashboard.sh (Mac)
├── make_shortcut.ps1 (Windows)
├── stable/
│   └── (Python code)
└── data/
    └── universe.csv
```

### Step 4: Install Python dependencies

Open PowerShell (Windows) or Terminal (Mac) and navigate to the project folder:

**Windows:**
```powershell
cd C:\Code\stable_market_board
pip install -r requirements.txt
```

**Mac:**
```bash
cd ~/Code/stable_market_board
pip3 install -r requirements.txt
```

Takes 1-3 minutes.

### Step 5: Set up your API key

Create a file named `.env` (just `.env`, no extension) in the project root with this content:

```
POLYGON_API_KEY=your_actual_polygon_key_here
HISTORY_YEARS=5
DB_PATH=./data/market.duckdb
UNIVERSE_PATH=./data/universe.csv
```

Replace `your_actual_polygon_key_here` with the key from Polygon. No quotes, no spaces.

**Windows one-liner to create the file:**
```powershell
@"
POLYGON_API_KEY=PASTE_YOUR_KEY_HERE
HISTORY_YEARS=5
DB_PATH=./data/market.duckdb
UNIVERSE_PATH=./data/universe.csv
"@ | Out-File -FilePath .env -Encoding ascii
```
Then open `.env` in Notepad and replace `PASTE_YOUR_KEY_HERE` with your actual key.

### Step 6: Sanity check your setup

Run the install check script to verify everything is wired up:

```
python install_check.py
```

This checks Python version, installed packages, .env file, universe.csv, and tests your API key against Polygon. If anything's wrong it'll say so.

### Step 7: Pull historical data (first time only)

The big one-time operation. Pulls 5 years of daily OHLCV for ~280 tickers.

```
python -m stable.ingest
```

**Expect 3-8 minutes.** You'll see a progress bar. Result is `data/market.duckdb`, about 30-50MB.

If something fails partway, just re-run the command. It's incremental and resumes from where it stopped.

### Step 8: Compute metrics

```
python -m stable.metrics
```

15-30 seconds. Computes moving averages, ATR, relative strength, new-high flags, etc. for every ticker for every day.

### Step 9: Start the dashboard

```
python -m stable.server
```

You'll see:
```
============================================================
 Stable Market Board
 Open in your browser: http://localhost:8000
============================================================
```

Open Chrome and go to **http://localhost:8000**.

### Step 10 (optional): Make a desktop shortcut

**Windows:** Run `make_shortcut.ps1` from PowerShell. This creates a "Stable Market Board" shortcut on your desktop. Double-click it any morning to run the full routine.

**Mac:** The `run_dashboard.sh` script in the project folder is your one-stop launcher. Right-click it in Finder and "Make Alias" to put on the desktop.

## Daily routine

Once setup is done, every morning:

1. **Double-click the desktop shortcut** (or run `run_dashboard.bat` / `run_dashboard.sh`)
2. Black window opens, runs ingestion + metrics + server (about 30 seconds total)
3. Browser opens to localhost:8000
4. Use the dashboard
5. When done, press Ctrl+C in the black window to stop the server (or close it)

Alternative if you just want to pull fresh data without restarting: click the **REFRESH button** in the top-right of the dashboard. Server is already running, it'll re-pull and reload in place.

## Tabs and what they show

- **Daily Board**: regime read, dominant/emerging/fading themes, index benchmark snapshot, universe breadth, ETF pulse cards (style rotation, risk pulse, sector rotation), 5-day theme rotation tracker
- **Themes**: all themes ranked with score, breadth, leadership, momentum metrics. Click any row to see its constituent names.
- **Breadth**: three charts. % above moving averages over time, daily impulse bars with new highs overlay, cumulative advance/decline line vs SPY. Theme dropdown filters chart 1 and 2 to a specific theme.
- **Extension**: "Too Hot" names extended above 50DMA (chase risk), plus "Fading/Weak" names losing trend
- **Clean Momentum**: filtered list of names meeting clean-momentum criteria (above 20/50 DMA, positive 5D, ATR ext in target range, volume confirming)

## Customization

Click the **gear icon** (top right, next to date) to open Settings. You can change:
- Which moving average periods to compute (10, 20, 21, 50, 200)
- The breadth "big move" threshold (default 4%)
- The ATR extension cutoff for "Too Hot"
- The Clean Momentum filter ranges

Changes to MA periods require re-running `python -m stable.metrics` to apply. Other settings apply immediately on save.

The universe of tickers and theme classifications lives in `data/universe.csv`. You can edit this file directly. After editing, re-run `python -m stable.ingest` (pulls history for any new tickers) and `python -m stable.metrics`.

## Stopping the server

Press **Ctrl+C** in the terminal window, or close the window.

If you close the window without Ctrl+C, Python may keep running in the background. If you later get "port 8000 already in use", run this to clean up:

**Windows:**
```powershell
Get-NetTCPConnection -LocalPort 8000 -ErrorAction SilentlyContinue | ForEach-Object {
    Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue
}
```

**Mac:**
```bash
lsof -ti:8000 | xargs kill -9
```

## Common problems

**"python is not recognized"** → Missed the "Add to PATH" checkbox during Python install. Reinstall Python with the box checked.

**"ModuleNotFoundError: No module named 'duckdb'"** → Didn't run `pip install -r requirements.txt`, or ran it with a different Python than what you're using. From inside the project folder, run it again.

**"401 Unauthorized" from Polygon** → API key is wrong, has whitespace, or subscription isn't active. Double-check the key in `.env` and at polygon.io/dashboard/keys.

**"Browser shows blank page"** → Hard-refresh with Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac) to bypass cache.

**"Port 8000 already in use"** → Old server still running. See "Stopping the server" above.

**"Ingestion is very slow"** → First-time pull is 5 years × 280 tickers. Expect 3-8 minutes depending on internet. Daily incremental pulls take ~10 seconds.

**"Dashboard data looks old"** → Either you haven't run ingest+metrics recently (use the Refresh button), or browser is showing cached HTML/JS (hard refresh).

## What this is NOT

- Not real-time. Daily OHLCV only, end-of-day data.
- Not a backtesting engine. This is a daily monitoring tool.
- Not a signal generator. The scores are descriptive, not prescriptive. They tell you what's happening, not what to trade.
- Not commercial software. No warranty, no support.

## License and use

Shared with you personally, as-is. Use it for your own trading. Don't redistribute broadly without asking. Don't sell it.

Polygon's Stocks Starter plan is personal use only. Your own subscription is fine for your individual use. Sharing access with others is a separate licensing question between you and Polygon.

Have fun.
