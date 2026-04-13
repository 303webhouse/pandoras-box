#!/usr/bin/env python3
"""
Patch script for Brief 2.2 + 2.3:
  2.2 — Personalized trading doc injection (full vs lite)
  2.3 — Wire pythia_events DB query into committee context

Run on VPS: python3 /tmp/patch_context_and_pythia.py
"""
import re
from pathlib import Path

SCRIPTS = Path("/opt/openclaw/workspace/scripts")
CONTEXT_FILE = SCRIPTS / "committee_context.py"
COMMITTEE_FILE = SCRIPTS / "pivot2_committee.py"


def patch_trading_docs():
    """Replace _load_trading_docs with _load_trading_docs_full and _load_trading_docs_lite."""
    content = CONTEXT_FILE.read_text()

    # Replace the existing _load_trading_docs function
    old_func = """def _load_trading_docs():
    parts=[]
    for n in ['trading-memory.md','open-positions.md','macro-economic-data.md']:
        try: parts.append(Path('/opt/openclaw/workspace/trading_docs/'+n).read_text())
        except: pass
    return '## TRADING CONTEXT\\n'+'\\n---\\n'.join(parts) if parts else ''"""

    new_funcs = '''TRADING_DOCS_DIR = Path("/opt/openclaw/workspace/trading_docs")


def _load_trading_docs_full() -> str:
    """Full context for PIVOT — memory + positions + macro."""
    parts = []
    for fn in ['trading-memory.md', 'open-positions.md', 'macro-economic-data.md']:
        try:
            parts.append((TRADING_DOCS_DIR / fn).read_text())
        except Exception:
            pass
    return "## TRADING CONTEXT\\n" + "\\n---\\n".join(parts) if parts else ""


def _load_trading_docs_lite() -> str:
    """Compressed context for analysts — positions + key rules only."""
    parts = []

    # Always include open positions
    try:
        parts.append((TRADING_DOCS_DIR / "open-positions.md").read_text())
    except Exception:
        pass

    # Extract just the don'ts and anti-bias sections from trading-memory.md
    try:
        memory = (TRADING_DOCS_DIR / "trading-memory.md").read_text()
        for heading in ["## DON'TS", "## ANTI-CONFIRMATION BIAS"]:
            # Try with and without emoji prefix
            for variant in [heading, heading.replace("##", "## \\U0001f6ab"), heading.replace("##", "## \\U0001f50d")]:
                if variant in memory:
                    start = memory.index(variant)
                    # Find next section boundary (--- or ## at start of line)
                    rest = memory[start + len(variant):]
                    end = len(memory)
                    for marker in ["\\n---", "\\n## "]:
                        pos = rest.find(marker)
                        if pos != -1 and start + len(variant) + pos < end:
                            end = start + len(variant) + pos
                    parts.append(memory[start:end].strip())
                    break
    except Exception:
        pass

    return "## TRADING CONTEXT (compressed)\\n" + "\\n---\\n".join(parts) if parts else ""


def _load_trading_docs(agent_type: str = "analyst") -> str:
    """Backwards-compatible wrapper."""
    if agent_type == "pivot":
        return _load_trading_docs_full()
    return _load_trading_docs_lite()'''

    if old_func in content:
        content = content.replace(old_func, new_funcs)
        print("[2.2] Replaced _load_trading_docs with full/lite versions")
    else:
        print("[2.2] WARNING: Could not find exact _load_trading_docs function. Trying regex...")
        pattern = r"def _load_trading_docs\(\):.*?return '## TRADING CONTEXT\\n'\+'\\n---\\n'\.join\(parts\) if parts else ''"
        if re.search(pattern, content, re.DOTALL):
            content = re.sub(pattern, new_funcs, content, flags=re.DOTALL)
            print("[2.2] Replaced via regex")
        else:
            print("[2.2] ERROR: Could not find _load_trading_docs at all!")
            return False

    # Update format_signal_context to accept agent_type parameter
    old_sig = "def format_signal_context(signal: dict, context: dict) -> str:"
    new_sig = 'def format_signal_context(signal: dict, context: dict, agent_type: str = "analyst") -> str:'
    if old_sig in content:
        content = content.replace(old_sig, new_sig)
        print("[2.2] Updated format_signal_context signature with agent_type param")
    else:
        print("[2.2] WARNING: format_signal_context signature not found (may already be updated)")

    # Update the _load_trading_docs() call inside format_signal_context
    old_call = "    td = _load_trading_docs()"
    new_call = "    td = _load_trading_docs(agent_type=agent_type)"
    if old_call in content:
        content = content.replace(old_call, new_call, 1)
        print("[2.2] Updated _load_trading_docs call to pass agent_type")

    CONTEXT_FILE.write_text(content)
    return True


def patch_pythia_events():
    """Add fetch_pythia_events function to committee_context.py."""
    content = CONTEXT_FILE.read_text()

    if "def fetch_pythia_events" in content:
        print("[2.3] fetch_pythia_events already exists, skipping")
        return True

    # Add import for os at top if not present
    if "import os" not in content:
        content = "import os\n" + content

    # Add the function before the last line or at the end
    pythia_func = '''

def fetch_pythia_events(ticker: str, limit: int = 5) -> str:
    """Fetch recent Pythia events for a ticker from Railway Postgres."""
    if not ticker:
        return ""
    try:
        import psycopg2
        DATABASE_URL = os.environ.get("DATABASE_URL", "")
        if not DATABASE_URL:
            return ""
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=10, sslmode="require")
        cur = conn.cursor()
        cur.execute("""
            SELECT alert_type, price, va_migration, poor_high, poor_low,
                   volume_quality, ib_high, ib_low, interpretation, timestamp
            FROM pythia_events
            WHERE ticker = %s
            ORDER BY timestamp DESC
            LIMIT %s
        """, (ticker.upper(), limit))
        rows = cur.fetchall()
        conn.close()
        if not rows:
            return ""
        lines = [f"## RECENT PYTHIA EVENTS -- {ticker}"]
        for r in rows:
            ts = str(r[9])[:19]
            alert = r[0] or "?"
            price = r[1] or "?"
            lines.append(
                f"  {ts} | {str(alert):20s} | ${price} | "
                f"VA-mig: {r[2]} | PH:{r[3]} PL:{r[4]} | vol:{r[5]} | IB:{r[6]}-{r[7]}"
            )
            if r[8]:
                lines.append(f"    >> {str(r[8])[:100]}")
        return "\\n".join(lines)
    except Exception as e:
        _log.warning(f"fetch_pythia_events failed: {e}")
        return ""
'''

    content = content.rstrip() + pythia_func
    CONTEXT_FILE.write_text(content)
    print("[2.3] Added fetch_pythia_events function")
    return True


def patch_committee_pythia_injection():
    """Add pythia_events injection to pivot2_committee.py run_committee function."""
    content = COMMITTEE_FILE.read_text()

    if "fetch_pythia_events" in content:
        print("[2.3] Pythia events injection already exists in committee, skipping")
        return True

    # Find a good injection point — after the MP levels block, before agent calls
    # Look for the combined analyst call block
    marker = "    # ── COMBINED ANALYSTS"
    if marker not in content:
        print("[2.3] ERROR: Could not find COMBINED ANALYSTS marker")
        return False

    injection = '''    # Inject Pythia events from Railway DB
    try:
        from committee_context import fetch_pythia_events
        pythia_events_block = fetch_pythia_events(signal.get("ticker", ""))
        if pythia_events_block:
            base_context = base_context + "\\n\\n" + pythia_events_block
    except Exception as e:
        log.warning("Failed to inject Pythia events: %s", e)

'''

    content = content.replace(marker, injection + marker)
    COMMITTEE_FILE.write_text(content)
    print("[2.3] Added Pythia events injection to run_committee")
    return True


def patch_committee_context_calls():
    """Update run_committee to pass agent_type to format_signal_context."""
    content = COMMITTEE_FILE.read_text()

    # The combined analyst call uses base_context from format_signal_context
    # We need to rebuild context for PIVOT with agent_type="pivot"
    # Find where pivot_context is built
    old_pivot_ctx = '    pivot_context = (\n        f"{base_context}\\n\\n"'
    if old_pivot_ctx in content:
        # Add a pivot-specific context rebuild before the pivot_context construction
        new_pivot_section = '''    # Rebuild context for PIVOT with full trading docs
    pivot_base = format_signal_context(signal, context, agent_type="pivot")
    # Re-inject enrichments that were added to base_context
    # (tech, econ, UW flow, portfolio, P&L, MP levels, pythia events are already in base_context)
    # For PIVOT, we use base_context (which has all enrichments) but swap the trading docs
    # Actually: base_context already has lite docs. For pivot, prepend full docs block.
    try:
        from committee_context import _load_trading_docs_full, _load_trading_docs_lite
        full_docs = _load_trading_docs_full()
        lite_docs = _load_trading_docs_lite()
        if full_docs and lite_docs and lite_docs in base_context:
            pivot_enriched = base_context.replace(lite_docs, full_docs, 1)
        elif full_docs:
            pivot_enriched = base_context + "\\n\\n" + full_docs
        else:
            pivot_enriched = base_context
    except Exception:
        pivot_enriched = base_context

    pivot_context = (
        f"{pivot_enriched}\\n\\n"'''
        content = content.replace(old_pivot_ctx, new_pivot_section)
        print("[2.2] Updated PIVOT to use full trading docs context")
    else:
        # Try finding it differently
        print("[2.2] WARNING: Could not find pivot_context construction. Checking alternate pattern...")
        if "pivot_context" in content:
            print("[2.2] pivot_context exists but pattern mismatch — manual check needed")
        else:
            print("[2.2] ERROR: No pivot_context found at all")

    COMMITTEE_FILE.write_text(content)


if __name__ == "__main__":
    print("=== Brief 2.2 + 2.3: Context Personalization + Pythia Events ===\n")

    print("Step 1: Patching trading docs (full/lite)...")
    ok1 = patch_trading_docs()

    print("\nStep 2: Adding fetch_pythia_events...")
    ok2 = patch_pythia_events()

    print("\nStep 3: Adding Pythia injection to run_committee...")
    ok3 = patch_committee_pythia_injection()

    print("\nStep 4: Updating PIVOT context for full docs...")
    patch_committee_context_calls()

    print("\n=== Verifying syntax... ===")
    import py_compile
    for f in ["committee_context.py", "pivot2_committee.py"]:
        try:
            py_compile.compile(str(SCRIPTS / f), doraise=True)
            print(f"  {f}: OK")
        except py_compile.PyCompileError as e:
            print(f"  {f}: FAILED — {e}")

    print("\n=== Testing doc loaders... ===")
    import sys
    sys.path.insert(0, str(SCRIPTS))
    try:
        from committee_context import _load_trading_docs_full, _load_trading_docs_lite
        full_len = len(_load_trading_docs_full())
        lite_len = len(_load_trading_docs_lite())
        print(f"  Full docs: {full_len} chars")
        print(f"  Lite docs: {lite_len} chars")
        print(f"  Reduction: {100 - (lite_len * 100 // full_len)}%")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n=== Done ===")
