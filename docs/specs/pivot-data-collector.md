# Pivot Data Collector — Implementation Spec
**Status:** Ready to build
**Depends on:** `composite-bias-engine.md` (Pivot feeds data to it), `factor-scoring.md` (scoring logic)
**Target:** OpenClaw agent ("Pivot") running on Hetzner VPS

## What This Does
Pivot is the "eyes and ears" of the bias system. It runs on a schedule, pulls market data from various sources, computes factor scores using the formulas in `factor-scoring.md`, and POSTs the results to the Trading Hub backend via `POST /api/bias/factor-update`.

## Architecture

```
PIVOT (Hetzner VPS)                           TRADING HUB (Railway)
─────────────────                             ──────────────────────

Cron Schedule                                 
    │                                         
    ├── Every 15 min (market hours)           
    │   ├── Pull yfinance data ──────────────► POST /api/bias/factor-update
    │   │   (HYG, TLT, RSP, SPY,              (credit_spreads, market_breadth,
    │   │    XLK, XLY, XLP, XLU,               sector_rotation, dollar_smile,
    │   │    DX-Y.NYB, ^VIX, ^VIX3M)           vix_term)
    │   │                                     
    │   └── Compute scores locally            
    │       using factor-scoring formulas     
    │                                         
    ├── Every 4 hours                         
    │   └── Pull CAPE ratio ─────────────────► POST /api/bias/factor-update
    │       (web scrape multpl.com)             (excess_cape)
    │                                         
    ├── Discord UW scrape (event-driven)      
    │   └── Analyze unusual options flow ────► POST /api/bias/factor-update
    │       from #unusual-whales channel        (supplemental signal)
    │                                         
    └── Health check every 5 min              
        └── POST /api/bias/health              (confirms Pivot is alive)
```

---

## Schedule Details

### Market Hours Pull (Every 15 minutes, Mon-Fri 9:30 AM - 4:00 PM ET)

**What to pull via yfinance:**

| Ticker | Factor(s) | Notes |
|--------|-----------|-------|
| HYG | Credit Spreads | iShares High Yield Corporate Bond |
| TLT | Credit Spreads | iShares 20+ Year Treasury |
| RSP | Market Breadth | Equal-weight S&P 500 |
| SPY | Market Breadth | Cap-weight S&P 500 |
| ^VIX | VIX Term Structure | CBOE Volatility Index |
| ^VIX3M | VIX Term Structure | 3-Month VIX |
| XLK | Sector Rotation | Technology Select |
| XLY | Sector Rotation | Consumer Discretionary |
| XLP | Sector Rotation | Consumer Staples |
| XLU | Sector Rotation | Utilities Select |
| DX-Y.NYB | Dollar Smile | US Dollar Index |

**Important:** yfinance data has a 15-minute delay for intraday. This is acceptable for bias factors — they measure trends, not tick-by-tick movement.

**Implementation:**
```python
import yfinance as yf
import requests
from datetime import datetime
import pytz

TRADING_HUB_URL = "https://your-railway-url.com"  # Set via env var
API_KEY = "your-api-key"  # Set via env var

TICKERS = ["HYG", "TLT", "RSP", "SPY", "^VIX", "^VIX3M", 
           "XLK", "XLY", "XLP", "XLU", "DX-Y.NYB"]

def is_market_hours():
    """Check if US market is open (9:30 AM - 4:00 PM ET, Mon-Fri)."""
    et = pytz.timezone("US/Eastern")
    now = datetime.now(et)
    if now.weekday() >= 5:  # Weekend
        return False
    market_open = now.replace(hour=9, minute=30, second=0)
    market_close = now.replace(hour=16, minute=0, second=0)
    return market_open <= now <= market_close

def pull_and_score():
    """Main function — pull data, compute scores, POST to backend."""
    if not is_market_hours():
        print("Market closed, skipping pull")
        return
    
    # Bulk download (faster than individual)
    data = yf.download(TICKERS, period="30d", progress=False, group_by="ticker")
    
    # Compute each factor score using formulas from factor-scoring.md
    factors = [
        compute_credit_spread_score(data),
        compute_breadth_score(data),
        compute_vix_term_score(data),
        compute_sector_rotation_score(data),
        compute_dollar_smile_score(data),
    ]
    
    # POST each to the backend
    for factor in factors:
        if factor:
            resp = requests.post(
                f"{TRADING_HUB_URL}/api/bias/factor-update",
                json=factor.dict(),
                headers={"Authorization": f"Bearer {API_KEY}"},
                timeout=10,
            )
            print(f"  {factor.factor_id}: {factor.signal} ({factor.score:+.2f}) → {resp.status_code}")
```

### Extended Hours Pull (Every 15 min, 4:00 AM - 9:30 AM and 4:00 PM - 8:00 PM ET)

During pre-market and after-hours, only pull VIX data (it trades extended hours):

| Ticker | Factor | Notes |
|--------|--------|-------|
| ^VIX | VIX Term Structure | Trades nearly 24 hours |
| ^VIX3M | VIX Term Structure | Same |

### CAPE Ratio Pull (Every 4 hours)

**Source:** Scrape from `https://www.multpl.com/shiller-pe` or use FRED API (series: `CAPE10`)

```python
def pull_cape():
    """Scrape current Shiller CAPE ratio."""
    import requests
    from bs4 import BeautifulSoup
    
    resp = requests.get("https://www.multpl.com/shiller-pe", timeout=10)
    soup = BeautifulSoup(resp.text, "html.parser")
    # Parse the current CAPE value from the page
    # (Exact selector may change — Pivot should handle parse errors gracefully)
    
    cape_value = parse_cape_from_page(soup)
    
    if cape_value:
        factor = compute_excess_cape_score(cape_value)
        post_factor_update(factor)
```

### Discord UW Scrape (Event-Driven)

**What Pivot watches:** The Unusual Whales Discord channel for large options flow alerts.
**What to look for:**
- Large put volume on SPY/QQQ/IWM (bearish flow)
- Unusual call volume on VIX (hedging = bearish for stocks)
- Big premium put buys on individual tech names (sector risk)

**This is a supplemental signal, not a primary factor.** Pivot should:
1. Parse UW alerts from Discord
2. Aggregate bearish vs bullish flow over rolling 4-hour window
3. If strongly skewed (>70% bearish flow by premium), POST as additional context to the bias engine
4. Format: POST to `/api/bias/factor-update` with `factor_id: "options_flow_supplemental"` and `source: "discord_uw"`

**Note:** Nick does not have real-time UW API access (15-min delay). Discord scraping is the primary method.

---

## Pivot Skill File Structure

If building as an OpenClaw skill:

```
skills/
  bias-data-collector/
    SKILL.md              # Instructions for Pivot
    pull_market_data.py   # Main yfinance pull + scoring
    pull_cape.py          # CAPE ratio scraper
    config.py             # API URLs, tickers, schedule
    requirements.txt      # yfinance, requests, beautifulsoup4, pytz
```

### SKILL.md for Pivot
```markdown
# Bias Data Collector

You are responsible for keeping the Pandora's Box trading platform's bias
system fed with fresh market data.

## Schedule
- Every 15 minutes during US market hours (9:30 AM - 4:00 PM ET, Mon-Fri):
  Run `pull_market_data.py`
- Every 15 minutes during extended hours (4 AM - 9:30 AM, 4 PM - 8 PM ET):
  Run VIX-only pull
- Every 4 hours: Run `pull_cape.py`

## What You Do
1. Pull market data from yfinance
2. Compute factor scores using the formulas in each function
3. POST results to the Trading Hub backend at POST /api/bias/factor-update
4. Log successes and failures

## Error Handling
- If yfinance fails, retry once after 30 seconds
- If the backend is unreachable, log the error and retry next cycle
- Never crash the schedule — individual factor failures should not stop other factors

## API Endpoint
POST {TRADING_HUB_URL}/api/bias/factor-update
Headers: Authorization: Bearer {API_KEY}
Body: JSON with factor_id, score, signal, detail, source, raw_data
```

---

## Health Check

Pivot should POST a heartbeat every 5 minutes:

```python
def health_check():
    requests.post(
        f"{TRADING_HUB_URL}/api/bias/health",
        json={"agent": "pivot", "timestamp": datetime.utcnow().isoformat()},
        timeout=5,
    )
```

The backend should track the last heartbeat. If no heartbeat for 30 minutes during market hours, the frontend should display a warning: "⚠️ Pivot data collector offline — bias readings may be stale."

---

## Environment Variables (Pivot VPS)

```
TRADING_HUB_URL=https://your-railway-app.up.railway.app
PIVOT_API_KEY=<shared secret for auth>
```

The backend should validate this key on `/api/bias/factor-update` and `/api/bias/health` endpoints.

---

## Build Checklist

- [ ] Create Pivot skill directory with SKILL.md
- [ ] Implement `pull_market_data.py` with yfinance bulk download
- [ ] Implement factor scoring functions (port from `factor-scoring.md`)
- [ ] Implement `pull_cape.py` web scraper
- [ ] Set up cron schedule (use system cron or Python `schedule` library)
- [ ] Add API key auth to backend factor-update endpoint
- [ ] Add health check endpoint to backend
- [ ] Add "Pivot offline" warning to frontend
- [ ] Test end-to-end: Pivot pull → POST → composite recompute → WebSocket broadcast
- [ ] Set up Discord UW monitoring (phase 2 — after core factors work)

## Future Enhancements (Phase 2+)
- Discord Unusual Whales flow analysis
- TradingView webhook relay for TICK data
- Sector-level breakdown alerts (e.g., "XLK -5% in 3 days")
- Cross-asset correlation monitoring (BTC + VIX + Credit moving together)
