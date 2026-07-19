"""
Brief #4: Add fetch_flow_events_context() to committee_context.py
Queries flow_events DB table for per-ticker options flow (now populated).
"""
from pathlib import Path

TARGET = Path("/opt/openclaw/workspace/scripts/committee_context.py")
content = TARGET.read_text(encoding="utf-8")

NEW_FUNC = '''
def fetch_flow_events_context(ticker: str) -> str:
    """
    Fetch per-ticker options flow from the local flow_events DB table.
    Returns compact text block for committee context.
    Populated by uw_flow_poller (fixed 2026-04-22 to use flow-per-expiry endpoint).
    """
    if not ticker:
        return ""
    cache_key = f"flow_events_{ticker.upper()}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    try:
        import psycopg2
        DATABASE_URL = os.environ.get("DATABASE_URL", "")
        if not DATABASE_URL:
            return ""
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")
        cur = conn.cursor()
        cur.execute("""
            SELECT call_premium, put_premium, total_premium,
                   call_volume, put_volume, pc_ratio,
                   flow_sentiment, captured_at
            FROM flow_events
            WHERE ticker = %s
              AND captured_at > NOW() - INTERVAL '24 hours'
            ORDER BY captured_at DESC
            LIMIT 10
        """, (ticker.upper(),))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            result = ""
            _cache_set(cache_key, result)
            return result
        # Use the most recent row as the primary snapshot
        latest = rows[0]
        call_prem = latest[0]
        put_prem = latest[1]
        total_prem = latest[2]
        call_vol = latest[3]
        put_vol = latest[4]
        pc_ratio = latest[5]
        sentiment = latest[6] or "UNKNOWN"
        captured = str(latest[7])[:16]
        lines = [f"## OPTIONS FLOW EVENTS ({ticker.upper()}) — as of {captured}"]
        if total_prem:
            lines.append(f"  Total Premium: ${total_prem:,.0f}")
        if call_prem and put_prem:
            lines.append(f"  Call Premium: ${call_prem:,.0f} | Put Premium: ${put_prem:,.0f}")
        if call_vol and put_vol:
            lines.append(f"  Call Volume: {call_vol:,} | Put Volume: {put_vol:,}")
        if pc_ratio:
            lines.append(f"  P/C Ratio: {pc_ratio:.2f}")
        lines.append(f"  Flow Sentiment: {sentiment}")
        if len(rows) > 1:
            lines.append(f"  ({len(rows)} snapshots in last 24h)")
        result = "\\n".join(lines)
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        _log.warning("fetch_flow_events_context failed for %s: %s", ticker, e)
        return ""
'''

# Insert before fetch_pythia_events (which is near end of file)
ANCHOR = "\ndef fetch_pythia_events("
if ANCHOR not in content:
    print("ERROR: anchor 'def fetch_pythia_events(' not found")
    exit(1)

if "def fetch_flow_events_context(" in content:
    print("Already patched — fetch_flow_events_context exists, skipping")
    exit(0)

content = content.replace(ANCHOR, NEW_FUNC + ANCHOR)
TARGET.write_text(content, encoding="utf-8")
print(f"Patched {TARGET} — added fetch_flow_events_context()")
