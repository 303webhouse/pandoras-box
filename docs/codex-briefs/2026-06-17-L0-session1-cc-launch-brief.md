# CC Launch Brief — L0 Session 1 (L0.2 allowlist + L0.1a suppression, SHADOW)

**Date:** 2026-06-17
**Parent brief:** `docs/codex-briefs/2026-06-17-L0-foundation-build-brief.md` (Titans-approved `3671c85`) — READ IT FIRST.
**Scope of THIS session:** L0.2 (liquid-ticker allowlist) + L0.1a (signal_type suppression gate, **SHADOW mode only**). Nothing else.
**Explicitly NOT this session:** L0.1b regime routing (gated on the sb3 ADX-regime promote), enforce-flip, scanner disable, Artemis, L0.5/L0.6.

---

## Purpose
Stand up the two unblocked pieces of L0's foundation: the liquid-universe allowlist that several gates depend on, and the suppression half of the routing gate — running in SHADOW so it tags what it *would* drop without dropping anything, so we can verify the populations before any enforce.

## Pre-flight (do all, in order)
1. `cmd /c "cd /d C:\trading-hub && git fetch && git status"` — confirm clean working tree at latest `origin/main`.
2. Create an isolated worktree/branch for L0 off current `main` HEAD — e.g. `git worktree add C:\th-l0 -b l0-foundation`. **Do NOT work in the `th-scoring` (`sb3-work`) or `th-security` (`sec-work`) worktrees.**
3. Read `PROJECT_RULES.md`, the parent L0 brief (above), and the master brief `docs/codex-briefs/2026-06-16-rebuild-stack-master-brief.md` §2/§11.

## Phase-0 (READ-ONLY — no writes, no migrations; complete BEFORE any build)
P0-1. **Re-query live `signal_type`** distinct + counts from the `railway` DB (DSN from `.mcp.json`, never print it). Confirm the suppress/keep sets in the parent brief §2 still match live values — do NOT trust the snapshot.
P0-2. **Read `process_signal_unified`** (`backend/signals/pipeline.py` L1141 → end) and `apply_scoring` (L229). Identify the exact line to insert the gate (top of `process_signal_unified`, BEFORE the `apply_scoring` call at ~L1187 and the `log_signal` at ~L1294). Capture the literal find/replace anchor.
P0-3. **Resolve the gate-leak (parent §7 item 6).** Read `backend/scheduler/bias_scheduler.py` L3575 and `backend/api/analytics.py` (analytics) ~L2079 — the two `log_signal` calls that bypass `process_signal_unified`. Determine if either is a LIVE signal-emit path. If yes, the gate must cover it (or that path must route through `process_signal_unified`). Document the finding.
P0-4. **Pick the shadow-tag field.** `gate_type` is ALREADY in use (`rsi`/`both`/`3-10`) — do NOT overload it. Prefer writing the shadow decision into `triggering_factors` jsonb under an `l0_shadow` key (no migration). If a dedicated column is genuinely needed, that's a reversible migration requiring an explicit dry-run + ATLAS sign-off — defer rather than block.
P0-5. **Confirm the liquid-universe membership** from `docs/strategy-reviews/signal-edge-validation-2026-06-16.md` (the `index_macro` + semis/tech buckets). That doc, not memory, is the source of truth for the allowlist.

## Tasks
### T1 — L0.2 liquid allowlist (pure code, no DB)
- Create `backend/config/liquid_universe.py`: an `is_liquid(ticker: str) -> bool` + the allowlist set, docstring citing the validation-doc buckets it came from (P0-5).
- Unit test: membership in/out, case-handling, a couple of known liquid (SPY, NVDA) and non-liquid (a random single-name) tickers.

### T2 — L0.1a suppression gate (SHADOW)
- Insert a single declarative suppression gate at the top of `process_signal_unified` (anchor from P0-2).
- Map keyed on `signal_type`:
  - SUPPRESS: `HOLY_GRAIL_1H`, `HOLY_GRAIL_15M`, `PULLBACK_ENTRY`, `TRAPPED_LONGS`.
  - SUPPRESS-IF-NON-LIQUID: `RESISTANCE_REJECTION` (suppress only when `not is_liquid(ticker)`).
  - KEEP (untouched): `GOLDEN_TOUCH`, `TRAPPED_SHORTS`, `TWO_CLOSE_VOLUME`, `APIS_CALL`, and every signal_type not named above.
- **SHADOW behavior:** compute the decision, write it to the `l0_shadow` tag (P0-4) — DO NOT drop, divert, or alter the signal's flow. One `L0_ENFORCE` config flag, default `False` (= shadow).
- Add a small shadow-measurement query (script under `scripts/` or a documented query) that reports, over the shadow window, how many signals were tagged would-suppress by signal_type, and asserts ZERO keepers were tagged.

## Gates / what NOT to do
- **SHADOW ONLY.** Do not flip `L0_ENFORCE`. Do not drop/divert any signal.
- **No regime routing** (that's L0.1b — gated on the sb3 promote + the `signals.regime`-persistence Phase-0 check; `signals.regime` is currently 100% NULL).
- **No scanner disable** (Holy Grail cron stays running this session).
- **No prod migration** this session — use the `triggering_factors` jsonb for the shadow tag.
- **Do NOT touch `score_v2_factors.sb3_shadow`** — use the `l0_shadow` namespace; sb3's shadow data is in flight.
- **Do NOT mutate `signal_type` or `strategy`** values anywhere.
- Dry-run before any `--apply`; no production write without explicit greenlight.
- Deploy ONLY outside 7:30 AM–2:00 PM MT. Atomic commits, explicit pathspecs, **never `git add .`**, commit via `git commit -F C:\temp\commitmsg.txt`.

## Output spec
- `backend/config/liquid_universe.py` + its test.
- The `process_signal_unified` gate edit (+ the `l0_shadow` tagging).
- The shadow-measurement query/script.
- Commit messages in `docs(...)` / `feat(l0):` style, on the `l0-foundation` branch. Do NOT merge to main without the shadow window + greenlight.

## Done definition
- `liquid_universe` tests pass.
- The suppression gate runs in SHADOW and tags NEW signals correctly: a query shows the would-suppress set = `HOLY_GRAIL_1H/15M` + `PULLBACK_ENTRY` + `TRAPPED_LONGS` + `RESISTANCE_REJECTION`-on-non-liquid, with ZERO keepers tagged.
- Nothing live-dropped; nothing deployed unless after-hours + greenlit.
- A stated plan to run the shadow window ≥1 week before proposing the enforce flip (which is a separate, separately-gated step).

## Olympus Impact
SHADOW-only ⇒ no committee-facing change this session (the feed/committee still see every signal; only a tag is added). A full Olympus committee pass on a known-good ticker is required at the ENFORCE flip, NOT here.
