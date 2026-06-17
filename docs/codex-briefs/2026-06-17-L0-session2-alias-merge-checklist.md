# L0.4 (alias / codename) -- After-Hours Merge & Verify Checklist

**Date:** 2026-06-17
**Brief:** `docs/codex-briefs/2026-06-17-L0-session2-alias-launch-brief.md`
**Branch built:** `l0-alias` (worktree `C:\th-l0-alias`) -- built-and-waiting, NOT merged.
**What it is:** additive codename display layer (Midas / Achilles / Hector / Apis / Kodiak / ...). Display-only -- no signal-flow, scoring, or DB change. Raw `signal_type` / `strategy` are frozen.

---

## STOP -- Pre-condition: time gate
Do NOT run this before **2:00 PM MT**. Pushing to `main` triggers a Railway redeploy (60-170s MCP downtime); the 7:30 AM - 2:00 PM MT deploy block applies. This whole checklist is an AFTER-CLOSE procedure.

## Step 0 -- Get CC's L0.4 build report (BEFORE merging)
Don't merge blind. Confirm from CC:
- [ ] **Coverage audit:** every read surface shows the codename -- frontend `formatSignalType` / `formatStrategyName`, `hub_mcp/tools/trade_ideas.py`, Discord `bot.py`, `signal_notifier.py`, committee prompts. Raw `signal_type` / `strategy` untouched everywhere.
- [ ] **P0-3 (Olympus safety):** did any committee prompt / skill branch on a raw `signal_type` the alias masks? (Additive design is the safety net even if yes -- but know the answer.)
- [ ] **Tests pass:** `strategy_aliases.py` units -- each mapping, multi-signal_type -> Achilles, unmapped -> raw fallback, None-safety.
- [ ] Anything unexpected in coverage / P0-3 -> pause and review before merge.

## Step 1 -- Merge `l0-alias` -> `main`
- [ ] `git fetch && git status` -- clean, on `main`, up to date with origin.
- [ ] Merge the branch as the unit (fast-forward if possible): bring `l0-alias` into `main`.
- [ ] Push `main` -> Railway auto-deploys.

## Step 2 -- Verify the deploy
- [ ] Wait ~60-170s for the Railway redeploy.
- [ ] Health endpoint returns 200.
- [ ] The `codename` field actually appears in the feed / MCP output (e.g. `hub_get_trade_ideas` returns `codename` alongside the raw `signal_type`).

## Step 3 -- Live Olympus committee pass (the gate's confirmation)
- [ ] Run ONE full committee pass on a known-good ticker.
- [ ] Confirm agents reason correctly with codenames present -- nothing keys on a now-masked raw string, no TORO-style confusion or fabrication.
- [ ] **Ordering:** this MUST come after the deploy -- the committee reads codenames through the hub, so you can't test the behavior until it's live. Merge-then-verify, not verify-then-merge.

## Step 4 -- Disposition
- [ ] **Clean** -> L0.4 is done / live. Update `docs/build-backlog.md` (mark L0.4 shipped).
- [ ] **Regression** -> additive design means raw values are preserved, so the failure degrades to cosmetic, not broken. Identify the specific surface; roll back if warranted (Step 5).

## Step 5 -- Rollback (if needed)
- [ ] `git revert` the merge commit on `main`, push -> Railway redeploys to the pre-L0.4 state.
- [ ] Low-risk: raw values were never removed, so reverting only drops the codename field.

---

**Reminder:** L0.4 has NO shadow window (unlike L0.1a / L0.3) -- display-only, so it's merge -> verify -> done in one after-hours sitting. L0.1a's shadow clock keeps running independently; don't touch its `L0_ENFORCE` flag here.
