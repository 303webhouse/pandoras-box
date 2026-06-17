# CC Launch Brief — L0 Session 3 (L0.3 APIS/KODIAK gating, SHADOW)

**Date:** 2026-06-17
**Parent brief:** `docs/codex-briefs/2026-06-17-L0-foundation-build-brief.md` §L0.3 (Titans-approved `3671c85`).
**Repo baseline:** `main` @ `8e11565`. Branch off current `main`. Worktrees in flight: `sb3-work`, `sec-work`, `l0-alias` (CC building L0.4) — don't collide.
**Scope of THIS session:** L0.3 only — gate the APIS_CALL label to non-liquid tickers; leave KODIAK_CALL ungated. Shadow-first (deploy inert behind a flag + retrospective measure). Concurrent with L0.1a's shadow window by design.

---

## ⚠️ ANCHOR CORRECTION (read first)
The parent brief / master brief named `macro_confluence.py::upgrade_signal_if_confluence` (L238). **That function is DEAD — zero callers; the whole `macro_confluence.py` module is orphaned (nothing imports it).** Do NOT edit it. The APIS_CALL label is applied at two LIVE sites (verified 2026-06-17):
- `backend/signals/pipeline.py:727` — `signal_data["signal_type"] = "APIS_CALL"` (inside `apply_scoring`)
- `backend/api/positions.py:718` — `sig['signal_type'] = "APIS_CALL"` (accept path)
- `backend/scoring/rank_trades.py:41` returns `"APIS_CALL"` — Phase-0: confirm whether it's the *decider* the two sites consume (gate once at the decider) or independent.

## Purpose
APIS edge is non-liquid-only — confirmed on LIVE data: APIS on **liquid** names n=93, avg **−0.126** (dominated by NVDA×48, GOOGL×26); APIS on **non-liquid** n=62, avg **+1.273**. So gating APIS to non-liquid withholds ~60% of fires — exactly the negative-edge ones. KODIAK: all 8 fires already non-liquid → nothing to gate, leave ungated (revisit n≥30, far off). Use the `is_liquid` allowlist shipped in L0.2.

## Pre-flight
1. `git fetch && git status` — clean, at `origin/main` (`8e11565`).
2. New worktree/branch off `main`: `git worktree add C:\th-l0-apis -b l0-apis`. Don't use the other worktrees.
3. Read `PROJECT_RULES.md` + parent brief §L0.3 + §7.

## Phase-0 (READ-ONLY — no writes)
P0-1. **Confirm the live APIS sites.** Read `pipeline.py:727` (its enclosing logic in `apply_scoring`) + `positions.py:718` + `rank_trades.py:41`. Determine: are the two assignment sites independent, or do both consume `rank_trades`'s decision? If a single decider exists, prefer gating there once.
P0-2. **Confirm KODIAK is untouched-safe.** Re-confirm (query) KODIAK_CALL has ~0 liquid fires; the gate is a no-op for it → leave KODIAK code paths alone.
P0-3. **Re-run the impact split** (DSN from `.mcp.json`, never print): APIS_CALL rows by `is_liquid(ticker)`, avg `outcome_pnl_pct` per group. Confirm liquid≈negative / non-liquid≈+1.2 still holds at build time.
P0-4. **L0.1a interaction note.** APIS overwrites `signal_type` at `pipeline.py:727`, which runs AFTER L0.1a's gate eval (top of `process_signal_unified`). So an L0.1a shadow tag may capture the PRE-upgrade `signal_type` (e.g. a bullish `PULLBACK_ENTRY` that becomes `APIS_CALL`). Not a blocker — document it as a known shadow-measurement edge for L0.1a; do not "fix" L0.1a here.

## Design (finalize in Phase-0)
- **Single eligibility helper.** Add `apis_eligible(ticker) -> bool` (= `not is_liquid(ticker)`) — ideally one helper called at both sites (or at the `rank_trades` decider if P0-1 confirms it).
- **Behind a flag, shadow-first.** `L0_APIS_ENFORCE` (default False, empty-safe env read per the repo pattern). When False: behavior UNCHANGED (APIS applies as today). When True: APIS only applies when `apis_eligible(ticker)`; otherwise keep the original `signal_type`.
- **Validation = retrospective measure** (no live tag needed — the gate logic is trivial and already unit-tested in L0.2). A read-only script reports, over the window, the APIS liquid/non-liquid split + per-group `outcome_pnl_pct`, confirming the liquid population stays negative-edge. Run it periodically alongside `l0_shadow_measure.py`.
- **KODIAK: no code change.**

## Tasks
1. `apis_eligible(ticker)` helper (+ tests; reuse `is_liquid` from `config.liquid_universe`).
2. Insert the guard at the live APIS site(s) from P0-1, behind `L0_APIS_ENFORCE` (default False). Original `signal_type` preserved when withheld.
3. `scripts/l0_apis_measure.py` (read-only) — APIS liquid/non-liquid split + pnl; never prints the DSN.
4. Unit tests: flag-False = unchanged behavior; flag-True = APIS withheld on liquid, applied on non-liquid; KODIAK unaffected either way.

## Gates / what NOT to do
- **Do NOT touch `macro_confluence.py`** (dead) or KODIAK paths.
- **`L0_APIS_ENFORCE` default False** — shadow deploy is behavior-INERT. No enforce flip this session.
- No DB migration; no overwrite of `signal_type` beyond conditioning the EXISTING APIS assignment.
- Use the `L0_APIS_ENFORCE` namespace — independent from L0.1a's `L0_ENFORCE` (so each flips when its own window clears).
- Deploy only outside 7:30 AM–2:00 PM MT. Atomic commits, explicit pathspecs, **never `git add .`**, commit via `git commit -F C:\temp\commitmsg.txt`.

## Output spec
`apis_eligible` helper + tests · the guarded APIS site(s) · `scripts/l0_apis_measure.py`. Commits in `feat(l0):` on `l0-apis`. Do NOT merge to main without greenlight; the shadow deploy is inert so it can merge after-hours, but the ENFORCE flip is separately gated.

## Done definition
- Helper + tests pass; with `L0_APIS_ENFORCE` unset, behavior is provably unchanged (regression test).
- `l0_apis_measure.py` reports the liquid/non-liquid split on live data.
- A stated plan: run the measure over the shadow window; before enforce, also ratify the `semis_ai_tech` allowlist (shared gate with L0.1a) + flip `L0_APIS_ENFORCE` only with greenlight + an Olympus committee pass (APIS is a feed/scoring label — enforce changes what the committee sees).

## Olympus Impact
Shadow deploy is INERT → no committee-facing change, no committee pass needed for the shadow merge. The committee pass IS required at the `L0_APIS_ENFORCE` flip (APIS labeling actually changes then). No new MCP tool; no data-source change.
