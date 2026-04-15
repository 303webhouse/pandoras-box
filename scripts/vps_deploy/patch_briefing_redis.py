#!/usr/bin/env python3
"""
Patch premarket_briefing.py to store synthesis via Railway API.
Patch committee_context.py to inject briefing history into PIVOT context.

Run on VPS: python3 /tmp/patch_briefing_redis.py
"""
from pathlib import Path

SCRIPTS = Path("/opt/openclaw/workspace/scripts")
BRIEFING = SCRIPTS / "premarket_briefing.py"
CONTEXT = SCRIPTS / "committee_context.py"
COMMITTEE = SCRIPTS / "pivot2_committee.py"


def patch_briefing():
    content = BRIEFING.read_text()

    if "store_briefing_railway" in content:
        print("[briefing] Railway storage already present, skipping")
        return

    store_func = '''
def store_briefing_railway(env: dict, briefing: dict):
    """POST briefing synthesis to Railway for Redis storage (7-day rolling)."""
    try:
        api_url = env.get("PANDORA_API_URL", "https://pandoras-box-production.up.railway.app/api")
        api_key = env.get("PIVOT_API_KEY", "")
        payload = json.dumps({
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "synthesis": briefing.get("synthesis", ""),
            "conviction": briefing.get("conviction", "MEDIUM"),
            "invalidation": briefing.get("invalidation", ""),
        }).encode()
        req = urllib.request.Request(
            f"{api_url}/briefing/premarket",
            data=payload,
            headers={"Content-Type": "application/json", "X-API-Key": api_key},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            log.info("Stored briefing in Railway Redis")
    except Exception as e:
        log.warning("Failed to store briefing: %s", e)

'''

    marker = "def main():"
    if marker in content:
        content = content.replace(marker, store_func + marker)
        print("[briefing] Added store_briefing_railway function")

    old_done = '    log.info("Pre-market briefing complete")'
    new_done = '    store_briefing_railway(env, briefing)\n\n    log.info("Pre-market briefing complete")'
    if old_done in content:
        content = content.replace(old_done, new_done, 1)
        print("[briefing] Wired store call into main()")

    BRIEFING.write_text(content)


def patch_context():
    content = CONTEXT.read_text()

    if "briefing:premarket" in content:
        print("[context] Briefing context already present, skipping")
        return

    inject_func = '''

def _get_premarket_briefing_context() -> str:
    """Load recent pre-market briefing summaries from Railway Redis."""
    try:
        import urllib.request
        import json as _bj
        api_url = os.environ.get("PANDORA_API_URL") or ""
        if not api_url:
            return ""
        req = urllib.request.Request(f"{api_url}/briefing/premarket?limit=5")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = _bj.loads(resp.read().decode("utf-8"))
        briefings = data.get("briefings", [])
        if not briefings:
            return ""
        lines = ["\\n\\n## RECENT PRE-MARKET BRIEFINGS (rolling 5 days)"]
        for entry in briefings:
            d = entry.get("date", "?")
            s = entry.get("synthesis", "")
            c = entry.get("conviction", "?")
            lines.append(f"**{d}** ({c}): {s[:300]}")
        return "\\n".join(lines)
    except Exception as e:
        _log.debug("Failed to load briefing history: %s", e)
        return ""
'''

    marker = "def _get_agent_feedback_context"
    if marker in content:
        content = content.replace(marker, inject_func + "\\n" + marker)
        # Oops, that would put a literal \\n. Let me fix:
        content = content.replace(inject_func + "\\n" + marker, inject_func + "\n" + marker)
        print("[context] Added _get_premarket_briefing_context")
    else:
        content = content.rstrip() + inject_func
        print("[context] Appended _get_premarket_briefing_context to end")

    CONTEXT.write_text(content)


def patch_committee():
    content = COMMITTEE.read_text()

    if "_get_premarket_briefing_context" in content:
        print("[committee] Already wired, skipping")
        return

    # Find pivot_feedback line
    marker = '    pivot_feedback = _get_agent_feedback_context("PIVOT")'
    if marker not in content:
        print("[committee] WARNING: Could not find pivot_feedback line")
        return

    new_block = marker + '''

    # Inject recent pre-market briefing history (PIVOT only, ~625 tokens max)
    try:
        from committee_context import _get_premarket_briefing_context
        briefing_ctx = _get_premarket_briefing_context()
    except Exception:
        briefing_ctx = ""'''

    content = content.replace(marker, new_block)
    print("[committee] Added briefing context fetch after pivot_feedback")

    # Inject briefing_ctx into pivot_context string
    # Find the f-string that builds pivot_context with pivot_feedback
    old = '        f"{pivot_feedback}"'
    if old in content:
        content = content.replace(old, '        f"{pivot_feedback}"\n        f"{briefing_ctx}"', 1)
        print("[committee] Injected briefing_ctx into PIVOT user message")
    else:
        print("[committee] WARNING: Could not inject into pivot_context f-string")

    COMMITTEE.write_text(content)


if __name__ == "__main__":
    print("=== Briefing Redis + PIVOT Injection ===\n")
    patch_briefing()
    print()
    patch_context()
    print()
    patch_committee()

    print("\n=== Syntax ===")
    import py_compile
    for f in ["premarket_briefing.py", "committee_context.py", "pivot2_committee.py"]:
        try:
            py_compile.compile(str(SCRIPTS / f), doraise=True)
            print(f"  {f}: OK")
        except py_compile.PyCompileError as e:
            print(f"  {f}: FAILED — {e}")
    print("\nDone.")
