#!/usr/bin/env python3
"""
Patch premarket_briefing.py to pull UW API data directly.
Adds: market tide, GEX levels, top flow, dark pool, economic calendar, earnings.
No more manual screenshots needed.

Run on VPS: python3 /tmp/patch_premarket_uw.py
"""
from pathlib import Path

SCRIPT = Path("/opt/openclaw/workspace/scripts/premarket_briefing.py")

content = SCRIPT.read_text()

# Add the UW data fetching function after load_trading_docs()
uw_fetch_func = '''

def fetch_uw_premarket_data(env: dict) -> str:
    """Pull pre-market data from UW API via Railway endpoints."""
    api_url = env.get("PANDORA_API_URL", "https://pandoras-box-production.up.railway.app/api")
    api_key = env.get("PIVOT_API_KEY", "")
    uw_key = env.get("UW_API_KEY", "")
    sections = []

    def _uw_get(path):
        """Direct UW API call."""
        if not uw_key:
            return None
        try:
            req = urllib.request.Request(
                f"https://api.unusualwhales.com{path}",
                headers={"Authorization": f"Bearer {uw_key}", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            log.debug("UW API %s failed: %s", path, e)
            return None

    # 1. Market Tide
    try:
        tide = _uw_get("/api/market/market-tide")
        if tide and tide.get("data"):
            latest = tide["data"][-1] if isinstance(tide["data"], list) else tide["data"]
            sections.append("## MARKET TIDE (UW API)")
            net_call = latest.get("net_call_premium", "?")
            net_put = latest.get("net_put_premium", "?")
            sections.append(f"  Net Call Premium: ${net_call}")
            sections.append(f"  Net Put Premium: ${net_put}")
            sections.append(f"  Net Volume: {latest.get('net_volume', '?')}")
    except Exception as e:
        log.debug("Market tide fetch failed: %s", e)

    # 2. SPY GEX
    try:
        gex = _uw_get("/api/stock/SPY/greek-exposure")
        if gex and gex.get("data"):
            data = gex["data"]
            total_call_gamma = sum(float(d.get("call_gamma", 0)) for d in data[:10])
            total_put_gamma = sum(float(d.get("put_gamma", 0)) for d in data[:10])
            net = total_call_gamma + total_put_gamma
            sections.append("## SPY GEX (UW API)")
            sections.append(f"  Net GEX (top 10 expirations): ${net/1e6:.1f}M")
            sections.append(f"  Call Gamma: ${total_call_gamma/1e6:.1f}M | Put Gamma: ${total_put_gamma/1e6:.1f}M")
            if net > 0:
                sections.append("  Regime: POSITIVE (compression — dealers dampen moves)")
            else:
                sections.append("  Regime: NEGATIVE (amplification — dealers amplify moves)")
    except Exception as e:
        log.debug("GEX fetch failed: %s", e)

    # 3. Top Flow (top net impact)
    try:
        flow = _uw_get("/api/market/top-net-impact")
        if flow and flow.get("data"):
            sections.append("## TOP NET IMPACT (UW API)")
            for item in flow["data"][:8]:
                ticker = item.get("symbol", "?")
                net = item.get("net_impact", "?")
                sections.append(f"  {ticker}: ${net}")
    except Exception as e:
        log.debug("Top flow fetch failed: %s", e)

    # 4. Dark Pool
    try:
        dp = _uw_get("/api/darkpool/recent")
        if dp and dp.get("data"):
            sections.append("## DARK POOL ACTIVITY (UW API)")
            for item in dp["data"][:5]:
                ticker = item.get("ticker", "?")
                vol = item.get("volume", "?")
                sections.append(f"  {ticker}: {vol} shares")
    except Exception as e:
        log.debug("Dark pool fetch failed: %s", e)

    # 5. Economic Calendar
    try:
        cal = _uw_get("/api/market/economic-calendar")
        if cal and cal.get("data"):
            today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            today_events = [e for e in cal["data"] if today_str in str(e.get("date", ""))]
            if today_events:
                sections.append("## TODAY'S ECONOMIC EVENTS (UW API)")
                for ev in today_events[:5]:
                    name = ev.get("name", "?")
                    time_str = ev.get("time", "?")
                    sections.append(f"  {time_str} — {name}")
    except Exception as e:
        log.debug("Economic calendar fetch failed: %s", e)

    # 6. Pre-market Earnings
    try:
        earn = _uw_get("/api/earnings/premarket")
        if earn and earn.get("data"):
            sections.append("## PRE-MARKET EARNINGS (UW API)")
            for e in earn["data"][:8]:
                sym = e.get("symbol", "?")
                name = e.get("full_name", "")
                est = e.get("street_mean_est", "?")
                mcap = e.get("marketcap", "")
                mcap_b = f"${int(mcap)/1e9:.0f}B" if mcap else "?"
                sections.append(f"  {sym} ({name}) — EPS est: ${est}, MCap: {mcap_b}")
    except Exception as e:
        log.debug("Earnings fetch failed: %s", e)

    # 7. News Headlines
    try:
        news = _uw_get("/api/news/headlines?limit=8")
        if news and news.get("data"):
            major = [n for n in news["data"] if n.get("is_major")]
            if major:
                sections.append("## MAJOR HEADLINES (UW API)")
                for n in major[:5]:
                    sections.append(f"  [{n.get('source', '?')}] {n.get('headline', '?')}")
            else:
                sections.append("## RECENT HEADLINES (UW API)")
                for n in news["data"][:5]:
                    sections.append(f"  [{n.get('source', '?')}] {n.get('headline', '?')}")
    except Exception as e:
        log.debug("News fetch failed: %s", e)

    return "\\n".join(sections) if sections else ""

'''

# Insert after load_trading_docs function
marker = 'def build_premarket_context(signals: list, trading_docs: str) -> str:'
if marker in content:
    # Change signature to accept uw_data
    content = content.replace(
        marker,
        'def build_premarket_context(signals: list, trading_docs: str, uw_data: str = "") -> str:'
    )
    # Insert the function before build_premarket_context
    content = content.replace(
        'def build_premarket_context(signals: list, trading_docs: str, uw_data: str = "") -> str:',
        uw_fetch_func + '\ndef build_premarket_context(signals: list, trading_docs: str, uw_data: str = "") -> str:'
    )
    print("Added fetch_uw_premarket_data function")
else:
    print("ERROR: Could not find build_premarket_context")

# Add UW data to the context
old_return = '    return "\\n".join(lines)'
# Find the one inside build_premarket_context (first occurrence)
idx = content.find(old_return)
if idx != -1:
    new_return = '''    if uw_data:
        lines.append("")
        lines.append(uw_data)

    return "\\n".join(lines)'''
    content = content[:idx] + new_return + content[idx + len(old_return):]
    print("Added UW data injection to context builder")

# Update main() to call fetch_uw_premarket_data
old_main_ctx = '        context = build_premarket_context(signals, trading_docs)'
new_main_ctx = '''        uw_data = fetch_uw_premarket_data(env)
        if uw_data:
            log.info("Fetched UW pre-market data (%d chars)", len(uw_data))

        context = build_premarket_context(signals, trading_docs, uw_data=uw_data)'''
if old_main_ctx in content:
    content = content.replace(old_main_ctx, new_main_ctx)
    print("Updated main() to fetch UW data")
else:
    print("WARNING: Could not find main() context line")

SCRIPT.write_text(content)

# Verify syntax
import py_compile
try:
    py_compile.compile(str(SCRIPT), doraise=True)
    print("premarket_briefing.py: OK")
except py_compile.PyCompileError as e:
    print(f"SYNTAX ERROR: {e}")

print("\nDone.")
