#!/usr/bin/env python3
"""
Patch VPS scripts for Committee Eyes brief:
  Part 3: Add build_uw_enrichment_context() to committee_context.py
  Part 4: Inject enrichment into pivot2_committee.py pipeline
  Part 5: Wire enrichment into premarket_briefing.py

Run on VPS: python3 /tmp/patch_committee_eyes.py
"""
from pathlib import Path

SCRIPTS = Path("/opt/openclaw/workspace/scripts")
CONTEXT = SCRIPTS / "committee_context.py"
COMMITTEE = SCRIPTS / "pivot2_committee.py"
BRIEFING = SCRIPTS / "premarket_briefing.py"


def part3_context_builder():
    """Add build_uw_enrichment_context to committee_context.py."""
    print("--- Part 3: Context builder ---")
    content = CONTEXT.read_text()

    if "build_uw_enrichment_context" in content:
        print("  Already exists, skipping")
        return

    func = '''

def build_uw_enrichment_context(ticker: str, api_url: str, api_key: str) -> str:
    """
    Fetch 6-point UW enrichment bundle from Railway (single call).
    Returns compact text block for committee context.
    """
    cache_key = f"uw_enrichment_{ticker.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    import urllib.request
    import urllib.error

    base = api_url.rstrip("/")
    try:
        req = urllib.request.Request(f"{base}/api/committee/enrichment/{ticker.upper()}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        _log.warning("UW enrichment fetch failed for %s: %s", ticker, e)
        return ""

    enrichment = data.get("enrichment", {})
    parts = [f"## UW ENRICHMENT ({ticker.upper()})"]

    # IV Rank
    iv = enrichment.get("iv_rank")
    if iv:
        rank = iv.get("iv_rank", "N/A")
        pct = iv.get("iv_pct", "N/A")
        curr = iv.get("current_iv", "N/A")
        parts.append(f"IV Rank: {rank} | IV Pct: {pct} | Current IV: {curr}")
        hi = iv.get("iv_high_52w")
        lo = iv.get("iv_low_52w")
        if hi and lo:
            parts.append(f"  52W Range: {lo} - {hi}")

    # Market Tide
    tide = enrichment.get("market_tide")
    if tide:
        net_call = tide.get("net_call_premium", "N/A")
        net_put = tide.get("net_put_premium", "N/A")
        net_vol = tide.get("net_volume", "N/A")
        parts.append(f"Market Tide: Call Prem ${net_call} | Put Prem ${net_put} | Vol {net_vol}")

    # Dark Pool
    dp = enrichment.get("dark_pool")
    if dp:
        parts.append(f"Dark Pool ({ticker.upper()}): {dp.get('total_prints', 0)} prints")
        for p in dp.get("top_prints", [])[:3]:
            sz = p.get("size", "?")
            px = p.get("price", "?")
            parts.append(f"  ${px} x {sz}")

    # Sector Flow
    sf = enrichment.get("sector_flow")
    if sf:
        posture = sf.get("risk_posture", "N/A")
        bull = ", ".join(sf.get("bullish_sectors", [])[:5]) or "none"
        bear = ", ".join(sf.get("bearish_sectors", [])[:5]) or "none"
        parts.append(f"Sector Flow: {posture} | Bull: {bull} | Bear: {bear}")

    # Max Pain
    mp = enrichment.get("max_pain")
    if mp:
        parts.append(f"Max Pain: ${mp.get('max_pain_strike')} (exp {mp.get('expiration')}, {mp.get('dte')} DTE)")

    # News
    news = enrichment.get("news_headlines")
    if news:
        parts.append(f"Headlines ({ticker.upper()}):")
        for h in news[:3]:
            parts.append(f"  [{h.get('source', '')}] {h.get('headline', '')}")

    result = "\\n".join(parts) if len(parts) > 1 else ""
    _cache_set(cache_key, result)
    return result
'''

    # Insert after build_mp_levels_context
    marker = "def build_mp_levels_context"
    idx = content.rfind(marker)
    if idx != -1:
        # Find end of that function (next def at same indent level)
        next_def = content.find("\ndef ", idx + 10)
        if next_def != -1:
            content = content[:next_def] + func + content[next_def:]
            print("  Inserted after build_mp_levels_context")
        else:
            content = content.rstrip() + func
            print("  Appended to end of file")
    else:
        content = content.rstrip() + func
        print("  Appended to end (marker not found)")

    CONTEXT.write_text(content)


def part4_inject_pipeline():
    """Inject UW enrichment into pivot2_committee.py."""
    print("--- Part 4: Pipeline injection ---")
    content = COMMITTEE.read_text()

    if "build_uw_enrichment_context" in content:
        print("  Already injected, skipping")
        return

    # Find the end of the UW flow injection block
    marker = '        log.warning("Failed to inject UW flow context: %s", e)'
    if marker not in content:
        print("  WARNING: Could not find UW flow context marker")
        return

    injection = '''

    # Inject UW enrichment data (IV rank, market tide, dark pool, sectors, max pain, news)
    try:
        from committee_context import build_uw_enrichment_context
        api_url = context.get("api_url") or os.environ.get("PANDORA_API_URL") or ""
        api_key_val = context.get("api_key") or os.environ.get("PIVOT_API_KEY") or ""
        ticker = signal.get("ticker", "")
        if ticker and api_url:
            enrichment_block = build_uw_enrichment_context(ticker, api_url, api_key_val)
            if enrichment_block:
                base_context = base_context + "\\n\\n" + enrichment_block
    except Exception as e:
        log.warning("Failed to inject UW enrichment context: %s", e)'''

    content = content.replace(marker, marker + injection, 1)
    COMMITTEE.write_text(content)
    print("  Injected enrichment block after UW flow context")


def part5_wire_briefing():
    """Wire enrichment into premarket briefing for SPY/QQQ."""
    print("--- Part 5: Premarket briefing ---")
    content = BRIEFING.read_text()

    if "committee/enrichment" in content:
        print("  Already wired, skipping")
        return

    # Find the context building line and add enrichment after it
    marker = "    context = build_premarket_context(signals, trading_docs, uw_data=uw_data)"
    if marker not in content:
        # Try older signature
        marker = "    context = build_premarket_context(signals, trading_docs)"
        if marker not in content:
            print("  WARNING: Could not find context build line")
            return

    enrichment_code = '''

    # Fetch UW enrichment for SPY + QQQ macro context
    for idx_ticker in ["SPY", "QQQ"]:
        try:
            enrich_url = f"{api_url}/committee/enrichment/{idx_ticker}"
            req = urllib.request.Request(enrich_url)
            with urllib.request.urlopen(req, timeout=15) as resp:
                enrich_data = json.loads(resp.read().decode("utf-8"))
            enrichment = enrich_data.get("enrichment", {})
            iv = enrichment.get("iv_rank") or {}
            tide = enrichment.get("market_tide") or {}
            sf = enrichment.get("sector_flow") or {}
            lines = [f"\\nUW Enrichment ({idx_ticker}):"]
            if iv:
                lines.append(f"  IV Rank: {iv.get('iv_rank', 'N/A')} | Pct: {iv.get('iv_pct', 'N/A')}")
            if tide:
                lines.append(f"  Tide: Call ${tide.get('net_call_premium', 'N/A')} | Put ${tide.get('net_put_premium', 'N/A')}")
            if sf:
                lines.append(f"  Sectors: {sf.get('risk_posture', 'N/A')}")
            context = context + "\\n".join(lines)
        except Exception as e:
            log.debug("Briefing enrichment failed for %s: %s", idx_ticker, e)'''

    content = content.replace(marker, marker + enrichment_code, 1)
    BRIEFING.write_text(content)
    print("  Added SPY/QQQ enrichment to briefing context")


if __name__ == "__main__":
    print("=== Committee Eyes — VPS Patches ===\n")

    part3_context_builder()
    print()
    part4_inject_pipeline()
    print()
    part5_wire_briefing()

    print("\n=== Syntax ===")
    import py_compile
    for f in ["committee_context.py", "pivot2_committee.py", "premarket_briefing.py"]:
        try:
            py_compile.compile(str(SCRIPTS / f), doraise=True)
            print(f"  {f}: OK")
        except py_compile.PyCompileError as e:
            print(f"  {f}: FAILED — {e}")

    print("\nDone.")
