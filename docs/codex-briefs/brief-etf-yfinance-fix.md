# Brief: Fix ETF yfinance Crash in Committee Pipeline

**Priority:** HIGH — Committee pipeline crashes when analyzing ETFs (QQQ, SMH, IWM, SPY, EFA, XLU, etc.). These are among the highest-value signal targets.

**Symptom:** Bridge log shows:
```
HTTP Error 404: {"quoteSummary":{"result":null,"error":{"code":"Not Found","description":"No fundamentals data found for symbol: QQQ"}}}
```

**Root cause:** The committee context builder calls yfinance's `quoteSummary` endpoint for fundamentals data (market cap, sector, etc.) as part of enrichment. ETFs don't have this data in yfinance, so it throws a 404 that isn't caught gracefully.

---

## Where to Fix

**VPS file:** `/opt/openclaw/workspace/scripts/committee_context.py`

This is the context builder that runs during committee pipeline. It enriches signals with market data before passing to the LLM agents.

**Also check:** `/opt/openclaw/workspace/scripts/pivot2_committee.py` — the orchestrator that calls the context builder.

---

## What to Fix

Find where yfinance fundamentals are fetched for the signal ticker. The call likely looks something like:

```python
stock = yf.Ticker(ticker)
info = stock.info  # This is what fails for ETFs
```

Wrap this in a try/except that:
1. Catches the 404 / empty result
2. Sets fundamentals fields to sensible defaults for ETFs
3. Continues the pipeline without crashing

**Suggested fix pattern:**
```python
try:
    stock = yf.Ticker(ticker)
    info = stock.info or {}
except Exception as e:
    logger.warning(f"Fundamentals unavailable for {ticker}: {e}")
    info = {}

# Use .get() with defaults for all fundamentals fields
market_cap = info.get("marketCap")  # Will be None for ETFs
sector = info.get("sector", "ETF" if not market_cap else "Unknown")
```

**ETF detection helper (optional but clean):**
```python
ETF_TICKERS = {"SPY", "QQQ", "IWM", "DIA", "SMH", "XLF", "XLE", "XLU", 
               "XLK", "XLV", "XLI", "XLP", "XLY", "XLB", "XLRE", 
               "EFA", "EEM", "GLD", "SLV", "TLT", "HYG", "LQD",
               "VTI", "VOO", "ARKK", "SOXX", "KRE", "XBI", "IBB",
               "FXI", "KWEB", "GDX", "GDXJ", "USO", "UNG"}

def is_etf(ticker: str) -> bool:
    return ticker.upper() in ETF_TICKERS
```

---

## Deployment

This is a VPS fix (not Railway). After editing:
```bash
ssh root@188.245.250.2
# Edit the file
nano /opt/openclaw/workspace/scripts/committee_context.py
# Restart the relevant services
systemctl restart pivot2-interactions
# The bridge cron picks up changes automatically
```

## Validation

After deploying, test by manually triggering a committee run on an ETF signal:
1. Find an active QQQ or SMH signal in Trade Ideas
2. Click the Analyze button in Discord
3. Confirm the committee completes without a 404 crash
4. Check bridge log: `tail -f /var/log/committee_bridge.log`

## Files Changed

- `/opt/openclaw/workspace/scripts/committee_context.py` — wrap yfinance fundamentals in try/except
- Possibly `/opt/openclaw/workspace/scripts/pivot2_committee.py` — if the crash originates there
