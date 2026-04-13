#!/usr/bin/env python3
"""
Patch script for Brief 2.1 — Combined Analyst Call

Deploys to VPS and modifies:
1. committee_prompts.py — adds COMBINED_ANALYST_SYSTEM_PROMPT
2. committee_parsers.py — updates parse_combined_analyst_response to include PYTHIA
3. pivot2_committee.py — replaces 4 individual analyst calls with 1 combined call

Run on VPS: python3 /tmp/patch_combined_analysts.py
"""
import re
import textwrap
from pathlib import Path

SCRIPTS = Path("/opt/openclaw/workspace/scripts")

# ── 1. Build COMBINED_ANALYST_SYSTEM_PROMPT ──────────────────

def build_combined_prompt():
    """Read existing prompts, extract rules (minus output format/examples), build combined."""
    prompts_file = SCRIPTS / "committee_prompts.py"
    content = prompts_file.read_text()

    # Extract each prompt's content between triple quotes
    def extract_prompt(var_name):
        pattern = rf'{var_name}\s*=\s*"""\\\n(.*?)"""'
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            raise ValueError(f"Could not find {var_name}")
        return match.group(1)

    toro = extract_prompt("TORO_SYSTEM_PROMPT")
    ursa = extract_prompt("URSA_SYSTEM_PROMPT")
    technicals = extract_prompt("TECHNICALS_SYSTEM_PROMPT")
    pythia = extract_prompt("PYTHIA_SYSTEM_PROMPT")

    def strip_output_and_examples(text):
        """Remove ## OUTPUT FORMAT, ## CONVICTION GUIDE, ## EXAMPLES, and ## Portfolio Context Rules sections."""
        lines = text.split("\n")
        result = []
        skip = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("## OUTPUT FORMAT") or stripped.startswith("## CONVICTION GUIDE") or stripped.startswith("## EXAMPLES") or stripped.startswith("## Portfolio Context Rules"):
                skip = True
                continue
            if skip and stripped.startswith("## "):
                skip = False
            if not skip:
                result.append(line)
        return "\n".join(result).rstrip()

    toro_rules = strip_output_and_examples(toro)
    ursa_rules = strip_output_and_examples(ursa)
    tech_rules = strip_output_and_examples(technicals)
    pythia_rules = strip_output_and_examples(pythia)

    combined = f'''You are running 4 distinct analyst perspectives on a trading signal in a single response. Output ALL FOUR sections in order, separated exactly as shown.

You will produce:
1. TORO (bull case)
2. URSA (bear case + risks)
3. TECHNICALS (chart structure assessment)
4. PYTHIA (market profile / auction state)

Each analyst has different expertise — do NOT blur them together. TORO finds bullish factors, URSA finds risks, TECHNICALS reads the chart, PYTHIA reads volume profile. They should reach DIFFERENT conclusions if the data supports it.

---

## TORO ANALYST RULES

{toro_rules}

---

## URSA ANALYST RULES

{ursa_rules}

---

## TECHNICALS ANALYST RULES

{tech_rules}

---

## PYTHIA ANALYST RULES

{pythia_rules}

---

## REQUIRED OUTPUT FORMAT (follow EXACTLY)

=== TORO ===
ANALYSIS: <3-5 sentence bull case>
CONVICTION: <HIGH|MEDIUM|LOW>

=== URSA ===
ANALYSIS: <3-5 sentence bear case>
CONVICTION: <HIGH|MEDIUM|LOW>

=== TECHNICALS ===
ANALYSIS: <3-5 sentence technical assessment>
CONVICTION: <HIGH|MEDIUM|LOW>

=== PYTHIA ===
STRUCTURE: <auction state>
LEVELS: <key MP levels>
ANALYSIS: <2-3 sentences>
CONVICTION: <HIGH|MEDIUM|LOW>

Each section is independent. Do not summarize across sections — that is PIVOT's job, not yours.'''

    return combined


def patch_prompts():
    """Add COMBINED_ANALYST_SYSTEM_PROMPT to committee_prompts.py."""
    prompts_file = SCRIPTS / "committee_prompts.py"
    content = prompts_file.read_text()

    if "COMBINED_ANALYST_SYSTEM_PROMPT" in content:
        print("[prompts] COMBINED_ANALYST_SYSTEM_PROMPT already exists, replacing...")
        # Remove existing combined prompt
        content = re.sub(
            r'\nCOMBINED_ANALYST_SYSTEM_PROMPT\s*=\s*""".*?"""',
            '',
            content,
            flags=re.DOTALL
        )

    combined = build_combined_prompt()
    # Escape any triple quotes in the combined text
    combined_escaped = combined.replace('"""', "'''")

    content = content.rstrip() + '\n\n\nCOMBINED_ANALYST_SYSTEM_PROMPT = """\\\n' + combined_escaped + '"""\n'
    prompts_file.write_text(content)
    print(f"[prompts] Added COMBINED_ANALYST_SYSTEM_PROMPT ({len(combined)} chars)")


# ── 2. Update parser to include PYTHIA ───────────────────────

def patch_parsers():
    """Update parse_combined_analyst_response to handle PYTHIA section."""
    parsers_file = SCRIPTS / "committee_parsers.py"
    content = parsers_file.read_text()

    # Replace the existing function with one that includes PYTHIA
    old_func_pattern = r'def parse_combined_analyst_response\(raw: str\) -> dict:.*?return result'

    new_func = '''def parse_combined_analyst_response(raw: str) -> dict:
    """
    Parse combined analyst response into four individual analyst dicts.
    Handles TORO, URSA, TECHNICALS, and PYTHIA sections.
    """
    sections = {}
    current_agent = None
    current_lines = []

    agent_names = ["TORO", "URSA", "TECHNICALS", "PYTHIA"]

    for line in raw.strip().split("\\n"):
        stripped = line.strip()
        upper = stripped.upper()

        matched_agent = None
        if upper.startswith("==="):
            for name in agent_names:
                if name in upper:
                    matched_agent = name
                    break

        if matched_agent:
            if current_agent:
                sections[current_agent] = "\\n".join(current_lines)
            current_agent = matched_agent
            current_lines = []
        else:
            current_lines.append(stripped)

    if current_agent:
        sections[current_agent] = "\\n".join(current_lines)

    result = {}
    for agent in agent_names:
        if agent in sections:
            result[agent.lower()] = parse_analyst_response(sections[agent], agent)
        else:
            result[agent.lower()] = {
                "agent": agent,
                "analysis": f"[ANALYSIS UNAVAILABLE - {agent} section not found in combined response]",
                "conviction": "MEDIUM",
            }

    return result'''

    content = re.sub(old_func_pattern, new_func, content, flags=re.DOTALL)
    parsers_file.write_text(content)
    print("[parsers] Updated parse_combined_analyst_response with PYTHIA support")


# ── 3. Replace 4 analyst calls with 1 combined call ─────────

def patch_run_committee():
    """Replace the 4 individual analyst calls with one combined call."""
    committee_file = SCRIPTS / "pivot2_committee.py"
    content = committee_file.read_text()

    # Find the 4 analyst call blocks: from "# ── TORO ANALYST ──" to just before "# ── PIVOT ──"
    toro_start = content.find("    # ── TORO ANALYST ──")
    pivot_start = content.find("    # ── PIVOT ──")

    if toro_start == -1 or pivot_start == -1:
        # Try alternate markers
        toro_start = content.find("    # -- TORO ANALYST --")
        pivot_start = content.find("    # -- PIVOT --")

    if toro_start == -1 or pivot_start == -1:
        print("[committee] ERROR: Could not find analyst call blocks. Manual patch needed.")
        print(f"  toro_start={toro_start}, pivot_start={pivot_start}")
        return False

    # Build the replacement block
    combined_block = '''    # ── COMBINED ANALYSTS (TORO + URSA + TECHNICALS + PYTHIA in one call) ──
    log.info("Calling combined analyst agent (TORO + URSA + TECHNICALS + PYTHIA)...")
    from committee_prompts import COMBINED_ANALYST_SYSTEM_PROMPT
    from committee_parsers import parse_combined_analyst_response

    combined_raw = call_agent(
        system_prompt=COMBINED_ANALYST_SYSTEM_PROMPT,
        user_message=_agent_context("ANALYSTS"),
        api_key=api_key,
        max_tokens=2500,
        temperature=0.3,
        agent_name="ANALYSTS",
        model=COMMITTEE_MODEL,
    )

    if combined_raw:
        parsed = parse_combined_analyst_response(combined_raw)
        toro_response = parsed["toro"]
        ursa_response = parsed["ursa"]
        technicals_response = parsed["technicals"]
        pythia_response = parsed["pythia"]
    else:
        fallback = {"analysis": "[ANALYSIS UNAVAILABLE — combined call timed out]", "conviction": "MEDIUM"}
        toro_response = {**fallback, "agent": "TORO"}
        ursa_response = {**fallback, "agent": "URSA"}
        technicals_response = {**fallback, "agent": "TECHNICALS"}
        pythia_response = {**fallback, "agent": "PYTHIA"}

    toro_raw = combined_raw
    ursa_raw = combined_raw
    technicals_raw = combined_raw
    pythia_raw = combined_raw

'''

    content = content[:toro_start] + combined_block + content[pivot_start:]
    committee_file.write_text(content)
    print("[committee] Replaced 4 individual analyst calls with 1 combined call")
    return True


# ── 4. Add import for COMBINED_ANALYST_SYSTEM_PROMPT ─────────

def patch_imports():
    """Ensure pivot2_committee.py imports from committee_prompts correctly."""
    committee_file = SCRIPTS / "pivot2_committee.py"
    content = committee_file.read_text()

    # The imports are done inline in run_committee, no top-level change needed
    # But let's verify the existing prompt imports
    if "from committee_prompts import" in content:
        # Check if it already imports what we need
        import_line = [l for l in content.split("\n") if "from committee_prompts import" in l]
        print(f"[imports] Existing prompt imports: {import_line}")

    print("[imports] Combined prompt imports are inline in run_committee — OK")


# ── Main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=== Brief 2.1: Combined Analyst Call Patch ===\n")

    print("Step 1: Building combined prompt...")
    patch_prompts()

    print("\nStep 2: Updating parser...")
    patch_parsers()

    print("\nStep 3: Patching run_committee...")
    ok = patch_run_committee()

    print("\nStep 4: Checking imports...")
    patch_imports()

    if ok:
        print("\n=== Verifying syntax... ===")
        import py_compile
        for f in ["committee_prompts.py", "committee_parsers.py", "pivot2_committee.py"]:
            try:
                py_compile.compile(str(SCRIPTS / f), doraise=True)
                print(f"  {f}: OK")
            except py_compile.PyCompileError as e:
                print(f"  {f}: FAILED — {e}")

    print("\n=== Done ===")
