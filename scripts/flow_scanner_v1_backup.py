"""
FLOW SCANNER — standalone, read-only UW options-flow radar for SPCX/AI volatility.

WHAT IT DOES
  Polls Unusual Whales order-level options flow on a tiered watchlist, clusters
  same-direction sweeps per ticker inside a rolling window, and prints ONE decisive
  line per qualifying cluster. It does the flow-reading FOR you: suppresses single
  sweeps (noise), fires only on loud clusters (signal), tags direction using UW's own
  bullish/bearish classification, and flags initiating vs. closing flow.

SAFETY PROPERTIES (why this can run the night before the IPO with zero deploy risk)
  - READ-ONLY. Hits only UW GET endpoints. Writes nothing to any DB, webhook, or file.
  - STANDALONE. Does not import or touch the hub. Own rate limiter. Close the terminal
    and it leaves no trace in production.
  - BUDGET-AWARE. Self-imposed cap (CALLS_PER_MIN_CAP) well under UW's 120/min account
    limit, with 429 backoff so it yields if UW pushes back. Leaves headroom for the hub.

HOW TO RUN (Windows, from repo root, so the UW key is injected from Railway env):
    cd /d C:\trading-hub
    railway run python scripts\flow_scanner.py

HOW TO TUNE LIVE (edit the CONFIG block below, restart):
  - Too quiet?  Lower MIN_CLUSTER_PREMIUM / MIN_SWEEPS, or widen ROLLING_WINDOW_MIN.
  - Too noisy?  Raise them.
  - Hub getting starved / seeing 429s?  Raise HOT_CADENCE_SEC / WARM_CADENCE_SEC.
"""

import os
import sys
import time
import asyncio
import json
from collections import deque, defaultdict
from datetime import datetime, timezone, timedelta

# Windows consoles default to cp1252 and choke on box/arrow glyphs. Force UTF-8.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import httpx
except ImportError:
    print("FATAL: httpx not installed. Run: pip install httpx --break-system-packages")
    sys.exit(1)

# ════════════════════════════════════════════════════════════════════════════
#  CONFIG  — everything you'd tune live lives here
# ════════════════════════════════════════════════════════════════════════════

UW_BASE = "https://api.unusualwhales.com"

# ---- Watchlist, tiered by how fast it matters -------------------------------
# bias: 'long' = catalyst expects upside (NDX adds, halo), 'short' = forced selling
#       (NDX removals), 'neutral' = just watching. Flow that CONTRADICTS the bias
#       is flagged specially — that's often the most informative print.
HOT = {  # polled every HOT_CADENCE_SEC
    "SPCX": "neutral",  # the detonator — ghost-guarded below
    "TSLA": "long", "RKLB": "long", "ALAB": "long", "CRWV": "long",
    "NBIS": "long", "TER": "long",
    "NVDA": "long", "AVGO": "long", "PLTR": "long", "ASTS": "long", "MU": "long",
    "SPY": "neutral", "QQQ": "neutral", "SMH": "neutral",
}
WARM = {  # polled every WARM_CADENCE_SEC
    "AMD": "long", "MRVL": "long", "ARM": "long", "SMCI": "long", "DELL": "long",
    "MSFT": "long", "GOOGL": "long", "AMZN": "long", "META": "long",
    "LRCX": "long", "KLAC": "long", "AMAT": "long", "COHR": "long",
    "LUNR": "long", "RDW": "long", "PL": "long", "IRDM": "neutral", "VSAT": "neutral",
    "IONQ": "long", "RGTI": "long", "QBTS": "long",
    "OKLO": "long", "SMR": "long", "VST": "long", "CEG": "long", "GEV": "long",
    "CIFR": "long", "WULF": "long", "APLD": "long", "CORZ": "long", "IREN": "long",
    # NDX rebalance REMOVALS — short bias, forced selling into 6/19 effective
    "CHTR": "short", "CTSH": "short", "INSM": "short", "VRSK": "short", "ZS": "short",
}

# ---- Cadence (seconds between polls per tier) --------------------------------
HOT_CADENCE_SEC = 30
WARM_CADENCE_SEC = 120

# ---- Rate-limit guard (UW account limit is 120/min; stay well under) ---------
CALLS_PER_MIN_CAP = 80        # hard self-cap; scanner never exceeds this
MAX_CONCURRENT_CALLS = 3      # smooth the draw instead of bursting
REQUEST_TIMEOUT_SEC = 8

# ---- Cluster detection ("tighter — only the loudest") ------------------------
ROLLING_WINDOW_MIN = 5        # orders within this window form a cluster
MIN_CLUSTER_PREMIUM = 500_000 # $ aggregate premium, same ticker+direction
MIN_SWEEPS = 3                # min order count in the cluster
# Indices fire way more flow → higher bar so they don't dominate the tape:
INDEX_MIN_PREMIUM = 1_500_000
INDEX_MIN_SWEEPS = 4
INDEX_TICKERS = {"SPY", "QQQ", "SMH"}
ALERT_COOLDOWN_MIN = 3        # don't re-alert same ticker+direction unless it grows
COOLDOWN_GROWTH = 1.5         # ...by >= this multiple of last alerted premium

# ---- Ghost-ticker guard (the dead SPAC-ETF that held SPCX trades ~$22) -------
SPCX_MIN_VALID_PRICE = 100.0  # real SpaceX can't print below this; reject corpse

# ---- Optional: auto-enroll high-conviction signals from the hub's Insights ---
# Best-effort. Reads the hub's OWN scored-signals endpoint (NOT a UW call, so it
# doesn't touch the 120/min budget). If it 401s or fails, scanner continues on the
# static universe. Tickers scoring >= DYNAMIC_MIN_SCORE join the hot tier.
DYNAMIC_FEED_ENABLED = True
DYNAMIC_FEED_URL = os.getenv("HUB_BASE_URL", "https://pandoras-box-production.up.railway.app") + "/api/trade-ideas/grouped"
DYNAMIC_API_KEY = os.getenv("PIVOT_API_KEY") or ""
DYNAMIC_MIN_SCORE = 80
DYNAMIC_MAX_TICKERS = 10      # cap so a flood of 80+ scores can't balloon the budget
DYNAMIC_POLL_SEC = 60


# ════════════════════════════════════════════════════════════════════════════
#  UW CLIENT  — minimal, self-contained, rate-limited, 429-aware
# ════════════════════════════════════════════════════════════════════════════

class RateLimiter:
    """Token-bucket-ish: caps calls/min and enforces minimum spacing between calls."""
    def __init__(self, calls_per_min):
        self.min_interval = 60.0 / calls_per_min
        self._last = 0.0
        self._lock = asyncio.Lock()
        self._call_times = deque()  # timestamps in last 60s

    async def acquire(self):
        async with self._lock:
            now = time.monotonic()
            wait = self.min_interval - (now - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
                now = time.monotonic()
            cutoff = now - 60.0
            while self._call_times and self._call_times[0] < cutoff:
                self._call_times.popleft()
            if len(self._call_times) >= CALLS_PER_MIN_CAP:
                sleep_for = self._call_times[0] + 60.0 - now
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                    now = time.monotonic()
            self._last = now
            self._call_times.append(now)


class UWClient:
    def __init__(self, api_key):
        self.api_key = api_key
        self.limiter = RateLimiter(CALLS_PER_MIN_CAP)
        self.sema = asyncio.Semaphore(MAX_CONCURRENT_CALLS)
        self._client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT_SEC,
            headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        )
        self.total_calls = 0
        self.total_429s = 0

    async def close(self):
        await self._client.aclose()

    async def flow_recent(self, ticker):
        """GET /api/stock/{ticker}/flow-recent → list of order-level records, or []."""
        url = f"{UW_BASE}/api/stock/{ticker.upper()}/flow-recent"
        for attempt in range(3):
            await self.limiter.acquire()
            async with self.sema:
                try:
                    r = await self._client.get(url)
                    self.total_calls += 1
                except (httpx.TimeoutException, httpx.TransportError):
                    await asyncio.sleep(1.5 * (attempt + 1))
                    continue
            if r.status_code == 429:
                self.total_429s += 1
                ra = r.headers.get("Retry-After")
                back = float(ra) if (ra and ra.replace(".", "").isdigit()) else 2.0 * (attempt + 1)
                print(f"  [rate-limit] UW 429 on {ticker} — backing off {back:.1f}s")
                await asyncio.sleep(back)
                continue
            if r.status_code >= 500:
                await asyncio.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code != 200:
                return []
            try:
                data = r.json()
            except Exception:
                return []
            rows = data if isinstance(data, list) else data.get("data", [])
            return rows if isinstance(rows, list) else []
        return []  # exhausted retries → empty, scanner continues


# ════════════════════════════════════════════════════════════════════════════
#  FLOW PARSING  — read UW's own tags to classify each order
# ════════════════════════════════════════════════════════════════════════════

def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default

def classify_order(rec):
    """
    Returns dict(direction, ask_side, initiating, premium, dte, otype) or None to skip.
    Uses UW's pre-computed `tags` (e.g. ['ask_side','bullish','sweep']).
    """
    if rec.get("canceled"):
        return None
    tags = [str(t).lower() for t in (rec.get("tags") or [])]
    if "bullish" in tags:
        direction = "BULLISH"
    elif "bearish" in tags:
        direction = "BEARISH"
    else:
        return None

    premium = _f(rec.get("premium"))
    vol = _f(rec.get("volume"))
    oi = _f(rec.get("open_interest"))

    dte = None
    exp = rec.get("expiry")
    if exp:
        try:
            ed = datetime.strptime(str(exp)[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            dte = max(0, (ed - datetime.now(timezone.utc)).days)
        except Exception:
            dte = None

    return {
        "direction": direction,
        "ask_side": "ask_side" in tags,
        "initiating": oi > 0 and vol > oi,
        "premium": premium,
        "dte": dte,
        "otype": rec.get("option_type", "?"),
    }

def passes_ghost_guard(ticker, rec):
    """Reject the dead SPCX SPAC-ETF corpse: sub-$100 underlying = not real SpaceX."""
    if ticker.upper() != "SPCX":
        return True
    up = _f(rec.get("underlying_price"))
    if up and up < SPCX_MIN_VALID_PRICE:
        return False
    return True


# ════════════════════════════════════════════════════════════════════════════
#  CLUSTER ENGINE  — dedupe orders, roll the window, detect loud clusters
# ════════════════════════════════════════════════════════════════════════════

class ClusterEngine:
    def __init__(self):
        # seen order ids (so an order counts once across overlapping polls)
        self.seen_ids = {}                  # id -> monotonic time first seen
        # rolling buffer of recent classified orders, keyed by (ticker, direction)
        self.buffers = defaultdict(deque)   # (tkr,dir) -> deque[(ts, info)]
        # last-alert bookkeeping for cooldown
        self.last_alert = {}                # (tkr,dir) -> (monotonic, premium)

    def _prune_seen(self):
        cutoff = time.monotonic() - (ROLLING_WINDOW_MIN * 60 * 2)
        for oid in [k for k, t in self.seen_ids.items() if t < cutoff]:
            self.seen_ids.pop(oid, None)

    def ingest(self, ticker, records):
        """Add new (unseen) classified orders for a ticker into rolling buffers."""
        now = time.monotonic()
        win_cut = now - ROLLING_WINDOW_MIN * 60
        added = 0
        for rec in records:
            oid = rec.get("id") or rec.get("flow_alert_id")
            if oid is not None:
                if oid in self.seen_ids:
                    continue
                self.seen_ids[oid] = now
            if not passes_ghost_guard(ticker, rec):
                continue
            info = classify_order(rec)
            if not info or info["premium"] <= 0:
                continue
            key = (ticker.upper(), info["direction"])
            self.buffers[key].append((now, info))
            added += 1
        # expire old orders from this ticker's buffers
        for d in ("BULLISH", "BEARISH"):
            buf = self.buffers[(ticker.upper(), d)]
            while buf and buf[0][0] < win_cut:
                buf.popleft()
        self._prune_seen()
        return added

    def evaluate(self, ticker):
        """Return a list of fired cluster-alert dicts for this ticker (after cooldown)."""
        out = []
        is_index = ticker.upper() in INDEX_TICKERS
        min_prem = INDEX_MIN_PREMIUM if is_index else MIN_CLUSTER_PREMIUM
        min_sweeps = INDEX_MIN_SWEEPS if is_index else MIN_SWEEPS
        now = time.monotonic()

        for direction in ("BULLISH", "BEARISH"):
            key = (ticker.upper(), direction)
            buf = self.buffers[key]
            if len(buf) < min_sweeps:
                continue
            total_prem = sum(i["premium"] for _, i in buf)
            if total_prem < min_prem:
                continue

            # cooldown: suppress unless premium grew materially since last alert
            la = self.last_alert.get(key)
            if la:
                last_t, last_prem = la
                if (now - last_t) < ALERT_COOLDOWN_MIN * 60 and total_prem < last_prem * COOLDOWN_GROWTH:
                    continue

            infos = [i for _, i in buf]
            ask_ct = sum(1 for i in infos if i["ask_side"])
            init_ct = sum(1 for i in infos if i["initiating"])
            dtes = [i["dte"] for i in infos if i["dte"] is not None]
            min_dte = min(dtes) if dtes else None

            self.last_alert[key] = (now, total_prem)
            out.append({
                "ticker": ticker.upper(),
                "direction": direction,
                "premium": total_prem,
                "sweeps": len(buf),
                "ask_pct": (ask_ct / len(buf)) if buf else 0,
                "init_pct": (init_ct / len(buf)) if buf else 0,
                "min_dte": min_dte,
            })
        return out


# ════════════════════════════════════════════════════════════════════════════
#  OUTPUT  — one decisive line per cluster
# ════════════════════════════════════════════════════════════════════════════

# ANSI colors (Windows Terminal / modern cmd support these)
G, R, Y, DIM, BOLD, X = "\033[92m", "\033[91m", "\033[93m", "\033[2m", "\033[1m", "\033[0m"

def fmt_prem(p):
    if p >= 1_000_000:
        return f"${p/1_000_000:.1f}M"
    return f"${p/1_000:.0f}K"

def bias_flag(ticker, direction, bias_map):
    """Flag when flow CONFIRMS or CONTRADICTS the catalyst-expected direction."""
    bias = bias_map.get(ticker.upper(), "neutral")
    if bias == "neutral":
        return ""
    expected = "BULLISH" if bias == "long" else "BEARISH"
    if direction == expected:
        return f" {G}✓confirms {bias}{X}"
    return f" {Y}⚠CONTRADICTS {bias}-bias{X}"

def print_alert(a, bias_map, dynamic_set):
    ts = datetime.now().strftime("%H:%M:%S")
    color = G if a["direction"] == "BULLISH" else R
    arrow = "▲" if a["direction"] == "BULLISH" else "▼"
    dte = "0DTE" if a["min_dte"] == 0 else (f"{a['min_dte']}DTE" if a["min_dte"] is not None else "—")
    aggr = "ask-side" if a["ask_pct"] >= 0.6 else ("mixed" if a["ask_pct"] >= 0.4 else "bid-side")
    init = "INIT" if a["init_pct"] >= 0.5 else "mixed"
    star = f" {BOLD}{Y}★HOT-SCORE{X}" if a["ticker"] in dynamic_set else ""
    flag = bias_flag(a["ticker"], a["direction"], bias_map)
    print(
        f"{DIM}{ts}{X} {color}{BOLD}{arrow} {a['ticker']:<5}{X} "
        f"{color}{a['direction']:<7}{X} "
        f"{BOLD}{fmt_prem(a['premium'])}{X} "
        f"{DIM}({a['sweeps']} sweeps · {aggr} · {init} · nearest {dte}){X}"
        f"{flag}{star}"
    )


# ════════════════════════════════════════════════════════════════════════════
#  DYNAMIC FEED  — pull tickers scoring >= 80 from the hub (best-effort, no UW cost)
# ════════════════════════════════════════════════════════════════════════════

async def fetch_dynamic_tickers(http):
    if not DYNAMIC_FEED_ENABLED:
        return set()
    headers = {}
    if DYNAMIC_API_KEY:
        headers["X-API-Key"] = DYNAMIC_API_KEY
    try:
        r = await http.get(DYNAMIC_FEED_URL, headers=headers, timeout=6)
        if r.status_code != 200:
            return set()
        data = r.json()
    except Exception:
        return set()
    # endpoint shape is grouped signals; pull tickers with score >= threshold
    found = {}
    groups = data.get("groups", data) if isinstance(data, dict) else data
    if isinstance(groups, dict):
        groups = list(groups.values())
    for g in (groups or []):
        items = g if isinstance(g, list) else [g]
        for sig in items:
            if not isinstance(sig, dict):
                continue
            tkr = (sig.get("ticker") or sig.get("symbol") or "").upper()
            score = _f(sig.get("score") or sig.get("composite_score") or sig.get("conviction_score"))
            if tkr and score >= DYNAMIC_MIN_SCORE:
                found[tkr] = max(found.get(tkr, 0), score)
    top = sorted(found.items(), key=lambda kv: kv[1], reverse=True)[:DYNAMIC_MAX_TICKERS]
    return {t for t, _ in top}


# ════════════════════════════════════════════════════════════════════════════
#  MAIN LOOP  — tiered scheduler
# ════════════════════════════════════════════════════════════════════════════

async def main():
    key = os.getenv("UW_API_KEY") or os.getenv("UNUSUAL_WHALES_API_KEY") or ""
    if not key:
        print(f"{R}FATAL: UW_API_KEY not in env. Launch with:  railway run python scripts\\flow_scanner.py{X}")
        sys.exit(1)

    uw = UWClient(key)
    engine = ClusterEngine()
    bias_map = {**HOT, **WARM}
    dynamic_set = set()

    hot_list = list(HOT.keys())
    warm_list = list(WARM.keys())
    est_hot = len(hot_list) * (60 / HOT_CADENCE_SEC)
    est_warm = len(warm_list) * (60 / WARM_CADENCE_SEC)

    print(f"{BOLD}══ FLOW SCANNER LIVE ══{X}")
    print(f"  Hot tier:  {len(hot_list)} names @ {HOT_CADENCE_SEC}s  (~{est_hot:.0f} calls/min)")
    print(f"  Warm tier: {len(warm_list)} names @ {WARM_CADENCE_SEC}s (~{est_warm:.0f} calls/min)")
    print(f"  Est. total ~{est_hot+est_warm:.0f}/min of 120 UW budget · cap {CALLS_PER_MIN_CAP}")
    print(f"  Cluster bar: ≥{fmt_prem(MIN_CLUSTER_PREMIUM)} & ≥{MIN_SWEEPS} sweeps "
          f"(index ≥{fmt_prem(INDEX_MIN_PREMIUM)} & ≥{INDEX_MIN_SWEEPS})")
    print(f"  Dynamic 80+ feed: {'ON' if DYNAMIC_FEED_ENABLED else 'OFF'}  ·  Ctrl-C to stop")
    print(f"{DIM}{'─'*72}{X}")

    next_hot = 0.0
    next_warm = 0.0
    next_dyn = 0.0

    async def scan(ticker):
        recs = await uw.flow_recent(ticker)
        engine.ingest(ticker, recs)
        for alert in engine.evaluate(ticker):
            print_alert(alert, bias_map, dynamic_set)

    try:
        while True:
            now = time.monotonic()

            # refresh dynamic hot-score tickers (cheap, non-UW)
            if DYNAMIC_FEED_ENABLED and now >= next_dyn:
                new_dyn = await fetch_dynamic_tickers(uw._client)
                if new_dyn != dynamic_set:
                    added = new_dyn - dynamic_set
                    if added:
                        print(f"{Y}  [dynamic] hot-score names now scanned: {', '.join(sorted(added))}{X}")
                    dynamic_set = new_dyn
                next_dyn = now + DYNAMIC_POLL_SEC

            # hot tier (static hot + any dynamic 80+ names)
            if now >= next_hot:
                targets = list(dict.fromkeys(hot_list + list(dynamic_set)))
                await asyncio.gather(*(scan(t) for t in targets))
                next_hot = now + HOT_CADENCE_SEC

            # warm tier
            if now >= next_warm:
                await asyncio.gather(*(scan(t) for t in warm_list))
                next_warm = now + WARM_CADENCE_SEC

            await asyncio.sleep(1.0)
    except KeyboardInterrupt:
        print(f"\n{DIM}stopped · {uw.total_calls} UW calls · {uw.total_429s} rate-limits{X}")
    finally:
        await uw.close()


if __name__ == "__main__":
    asyncio.run(main())
