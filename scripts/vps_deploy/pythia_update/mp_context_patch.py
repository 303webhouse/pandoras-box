"""Patch to append build_mp_levels_context to committee_context.py"""

PATCH = '''

def build_mp_levels_context(ticker: str, api_url: str, api_key: str) -> str:
    """Fetch cached MP levels for a ticker from the Pandora API."""
    if not ticker or not api_url:
        return ""

    import urllib.request
    import json as _json

    base = api_url.rstrip("/")
    url = f"{base}/api/mp/levels/{ticker.upper()}"
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    try:
        req = urllib.request.Request(url=url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = _json.loads(resp.read().decode("utf-8"))
    except Exception:
        return ""

    if not data.get("available") or not data.get("levels"):
        return ""

    levels = data["levels"]
    vah = levels.get("vah", "?")
    val = levels.get("val", "?")
    poc = levels.get("poc", "?")
    ib_high = levels.get("ib_high")
    ib_low = levels.get("ib_low")
    ib_width = levels.get("ib_width")
    ib_avg = levels.get("ib_avg_width")
    ib_class = levels.get("ib_classification", "")
    va_migration = levels.get("va_migration", "UNKNOWN")
    prior_poc = levels.get("prior_poc")
    high_q = levels.get("high_quality", "")
    low_q = levels.get("low_quality", "")

    lines = [f"## MARKET PROFILE LEVELS ({ticker.upper()})"]
    lines.append(f"Prior Session: VAH ${vah} | POC ${poc} | VAL ${val}")
    if prior_poc:
        lines.append(f"Value Area Migration: {va_migration} (prior POC was ${prior_poc})")
    else:
        lines.append(f"Value Area Migration: {va_migration}")
    if ib_high and ib_low:
        ib_line = f"Initial Balance: ${ib_low} - ${ib_high}"
        if ib_width:
            ib_line += f" (width: ${ib_width}"
            if ib_avg:
                ib_line += f", {ib_class} vs ${ib_avg} avg"
            ib_line += ")"
        lines.append(ib_line)
    if high_q == "POOR":
        lines.append("Poor High detected — unfinished auction at session high")
    if low_q == "POOR":
        lines.append("Poor Low detected — unfinished auction at session low")

    return "\\n".join(lines)
'''

if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "/opt/openclaw/workspace/scripts/committee_context.py"
    with open(target, "a") as f:
        f.write(PATCH)
    print(f"Appended build_mp_levels_context to {target}")
