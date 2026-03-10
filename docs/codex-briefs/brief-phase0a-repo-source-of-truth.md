# Brief: Phase 0A — Repo Source of Truth

**Priority:** CRITICAL — This blocks all other cleanup work. The repo must contain every production-critical file before any other Phase 0 work begins.
**Target:** VPS (SSH to `188.245.250.2`) → local repo → push to `main`
**Estimated time:** 45–60 minutes
**Prerequisites:** SSH access to VPS (`root@188.245.250.2`), GitHub push access

---

## Context

An external audit (GPT-5.4, March 9 2026) found that the repo is not a complete source of truth. Multiple production-critical scripts exist ONLY on the VPS and are not tracked in git. Additionally, two copies of `committee_interaction_handler.py` have materially diverged, docs contain stale/contradictory information, and `config/.env` has real credentials committed to the repo.

**This brief establishes one canonical codebase before any other cleanup begins.**

---

## Task 1: Inventory VPS-only scripts

SSH to `188.245.250.2` and list every Python script in the production directory:

```bash
ssh root@188.245.250.2 "ls -la /opt/openclaw/workspace/scripts/*.py"
```

Cross-reference against what's already in the repo at `scripts/`. The following files are KNOWN to be missing from the repo based on imports and cron references:

- `committee_parsers.py` — imported by `pivot2_committee.py`
- `committee_decisions.py` — imported by `pivot2_committee.py`
- `committee_outcomes.py` — outcome matcher (cron job: nightly 11 PM ET)
- `committee_analytics.py` — pattern analytics
- `committee_review.py` — weekly self-review (cron job: Saturday 9 AM MT)
- `pivot2_trade_poller.py` — trade poller (cron job: every 15 min market hours)
- `pivot2_brief.py` — morning/EOD briefs (cron job: 9:30 AM ET / 5 PM ET)
- `pivot2_twitter.py` — Twitter sentiment (cron job: every 30 min, currently disabled)
- `ibkr_quotes.py` — IBKR market data quotes (cron job: every 1 min market hours)

There may be others. **Capture ALL `.py` files from VPS, not just the known missing ones.**

## Task 2: Pull VPS scripts into repo

Copy every VPS-only script into the local repo at `scripts/`:

```bash
# From local machine — pull all VPS scripts
scp root@188.245.250.2:/opt/openclaw/workspace/scripts/*.py scripts/
```

**DO NOT overwrite files that already exist in the repo without diffing first.** For files that exist in BOTH locations:

```bash
# For each file that exists in both places, diff them:
diff scripts/<filename>.py <(ssh root@188.245.250.2 "cat /opt/openclaw/workspace/scripts/<filename>.py")
```

If they've diverged, the VPS copy is the production truth. Replace the repo copy with the VPS copy.

### Files that exist in both `scripts/` and `openclaw/scripts/`:

The repo currently has `committee_interaction_handler.py` in TWO places:
- `scripts/committee_interaction_handler.py`
- `openclaw/scripts/committee_interaction_handler.py`

These have materially diverged. **Resolution:**
1. Diff both repo copies against the VPS live copy at `/opt/openclaw/workspace/scripts/committee_interaction_handler.py`
2. The VPS copy is canonical (it's what's actually running)
3. Put the canonical copy in `scripts/committee_interaction_handler.py`
4. Delete `openclaw/scripts/committee_interaction_handler.py`
5. If `openclaw/scripts/` has other files besides `ibkr_poller.py`, move them to `scripts/` too — we want one script directory

Similarly, check `ibkr_poller.py`:
- `openclaw/scripts/ibkr_poller.py` exists in repo
- Diff against VPS copy, take VPS version if different
- Move to `scripts/ibkr_poller.py`, delete from `openclaw/scripts/`

## Task 3: Verify completeness

After pulling all files, verify every reference resolves:

```bash
# Every file referenced in cron jobs exists in scripts/
grep -oP '"command":\s*"python3\s+/opt/openclaw/workspace/scripts/\K[^"]+' openclaw/cron/jobs.json | while read f; do
  [ -f "scripts/$f" ] && echo "✅ $f" || echo "❌ MISSING: $f"
done

# Every Python import in pivot2_committee.py resolves to a file in scripts/
grep -oP 'from\s+\K\w+' scripts/pivot2_committee.py | sort -u | while read mod; do
  [ -f "scripts/${mod}.py" ] && echo "✅ ${mod}.py" || echo "⚠️ CHECK: ${mod}.py (may be stdlib)"
done
```

## Task 4: Fix stale documentation

### README.md
Find and remove any reference to `git pull origin main` as a VPS deploy method. The VPS has no git repo. Correct deploy instructions:

Find:
```
git pull origin main
```
Or any similar line suggesting git-based VPS deployment.

Replace with / ensure it says:
```
# VPS has no git repo. Deploy via:
# Option A: rsync from local clone (bash pivot/deploy.sh --update)
# Option B: Direct edit on VPS + systemctl restart <service>
```

### Gemini references
Search the entire repo for stale Gemini/OpenRouter references:

```bash
grep -ri "gemini\|openrouter" --include="*.md" --include="*.py" --include="*.json" -l
```

For each file found:
- If it's a doc file: update to say "Anthropic API direct — Haiku for analysis, Sonnet for synthesis"
- If it's code: check whether the code actually uses Gemini/OpenRouter or if it's just a comment. Fix accordingly.
- **Exception:** `config/.env` has a `GEMINI_API_KEY` — this file gets removed entirely in Task 5.

### CLAUDE.md cross-check
Verify `CLAUDE.md` does NOT contain:
- Any mention of `git pull` for VPS deployment
- Any mention of Gemini or OpenRouter as the active LLM provider
- Any reference to `open_positions` table as the active positions table (it's deprecated — `unified_positions` is canonical)

If any of these are found, correct them.

## Task 5: Remove committed secrets

`config/.env` contains live credentials (Redis password, DB password, Discord bot token, API keys). It's in `.gitignore` but was committed before that entry was added.

```bash
# Remove from git tracking (keeps local file but stops tracking)
git rm --cached config/.env

# Verify it's gone from staging
git status
# Should show: deleted: config/.env
```

**DO NOT delete the local file** — just untrack it from git.

**Note for Nick:** After this deploys, you should rotate any credentials that were in that file (Redis password, DB password, Discord bot token, API keys). The old values are still in git history. A full history purge (`git filter-branch` or `bfg`) is recommended but can be done later.

## Task 6: Clean up openclaw/scripts/ directory

After moving all scripts to `scripts/`, the `openclaw/scripts/` directory should be empty or removed. If `openclaw/` still has value (README.md, cron/jobs.json), keep the directory but remove the `scripts/` subdirectory:

```bash
# If openclaw/scripts/ is now empty
rm -rf openclaw/scripts/
```

Keep `openclaw/cron/jobs.json` and `openclaw/README.md` — those are still useful reference.

## Task 7: Commit and push

```bash
git add scripts/
git add -u  # picks up deletions and modifications
git commit -m "Phase 0A: Repo source of truth — pull all VPS scripts, resolve duplicates, fix docs, remove committed secrets"
git push origin main
```

---

## Definition of Done

1. Every `.py` file at `/opt/openclaw/workspace/scripts/` on VPS has a matching copy in `scripts/` in the repo
2. Every file referenced in `openclaw/cron/jobs.json` exists in `scripts/`
3. Every import in `pivot2_committee.py` resolves to a file in `scripts/`
4. Only ONE copy of `committee_interaction_handler.py` exists (in `scripts/`)
5. Only ONE copy of `ibkr_poller.py` exists (in `scripts/`)
6. No doc mentions `git pull` as VPS deploy method
7. No doc references Gemini or OpenRouter as the active LLM provider
8. `config/.env` is not tracked by git (still exists locally, just untracked)
9. All changes pushed to `main`

---

## What this brief does NOT do

- Does NOT fix auth (that's Phase 0B)
- Does NOT fix positions migration (that's Phase 0C)
- Does NOT fix frontend dead endpoints (that's Phase 0D)
- Does NOT rotate credentials (Nick does that manually after deploy)
- Does NOT change any runtime behavior — this is purely making the repo match production

---

## Post-build checklist

After CC completes this brief:
1. Verify Railway auto-deploy succeeds (no import errors from new files): `curl https://pandoras-box-production.up.railway.app/health`
2. Verify VPS services still running (this brief doesn't touch VPS runtime): `ssh root@188.245.250.2 "systemctl status openclaw pivot2-interactions pivot-collector"`
3. Nick: rotate credentials that were in `config/.env` (Redis, DB, Discord token, API keys)
4. Update `DEVELOPMENT_STATUS.md` with Phase 0A completion
