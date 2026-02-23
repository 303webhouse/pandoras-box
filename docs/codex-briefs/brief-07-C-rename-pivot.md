# Brief 07-C — "Pivot II" → "Pivot" Rename

**Phase:** 2 (PARALLEL — no dependencies, pure text replacement)
**Touches:** All `.md`, `.py`, `.html`, `.js` files with "Pivot II" or "Pivot 2" references
**Estimated time:** 15-20 minutes

---

## Task

Search-and-replace all human-readable references to "Pivot II" or "Pivot 2" with just "Pivot" across the entire codebase. This is a branding cleanup — the system is simply called "Pivot" now.

## Rules

### DO rename:
- All occurrences of "Pivot II" (case-sensitive) → "Pivot"
- All occurrences of "Pivot 2" (when referring to the bot name, not filenames) → "Pivot"
- Comment strings, docstrings, README text, UI labels, log messages
- All `.md` documentation files

### DO NOT rename:
- **Filenames:** `pivot2_committee.py`, `pivot2_*.py` — these stay as-is (changing would break imports, cron jobs, systemd services)
- **Systemd service names:** `pivot2-interactions.service`, etc.
- **Import statements** referencing `pivot2_*` modules
- **Variable names** like `pivot2_committee` in code
- **Git history** — no rewriting

## Also fix while you're in there

The `AGENT_BOOTSTRAP.md` file has this incorrect line:
> **LLM is Gemini Pro via OpenRouter**, not Claude.

Change it to:
> **LLM is Claude Haiku/Sonnet via OpenRouter**, not GPT.

(The system prompt reference on the same line can stay as-is.)

## Search commands

```bash
# Find all occurrences (from repo root)
grep -rn "Pivot II" --include="*.md" --include="*.py" --include="*.html" --include="*.js" .
grep -rn "Pivot 2" --include="*.md" --include="*.py" --include="*.html" --include="*.js" .

# Verify nothing left after changes
grep -rn "Pivot II\|Pivot 2" --include="*.md" --include="*.py" --include="*.html" --include="*.js" . | grep -v "pivot2_" | grep -v "pivot2-"
```

## Known files likely containing "Pivot II"

These are the most likely — but do a full grep to catch everything:

- `CLAUDE.md`
- `DEVELOPMENT_STATUS.md`
- `PROJECT_RULES.md`
- `AGENT_BOOTSTRAP.md`
- `README.md` (if it exists)
- `docs/` — various documentation files
- `frontend/index.html` — page title, UI text
- `frontend/app.js` — any bot name references
- VPS-targeted files in `pivot/` directory (if present in repo)
- `backend/discord_bridge/bot.py` — log messages, bot status text

## Verification

```bash
# Should return ZERO results (excluding pivot2_ filenames and pivot2- service names)
grep -rn "Pivot II\|Pivot 2" --include="*.md" --include="*.py" --include="*.html" --include="*.js" . | grep -v "pivot2_" | grep -v "pivot2-"
```

## Commit

```
docs: rename "Pivot II" to "Pivot" across codebase (brief 07-C)
```

## Definition of Done

- [ ] Zero occurrences of "Pivot II" in human-readable text
- [ ] Zero occurrences of "Pivot 2" (as a name, not filename/variable)
- [ ] AGENT_BOOTSTRAP.md LLM reference corrected from "Gemini Pro" to "Claude Haiku/Sonnet"
- [ ] All `pivot2_*.py` filenames and imports unchanged
- [ ] All systemd service names unchanged
- [ ] App still starts without import errors
