# CC Launch Brief — L0 Session 2 (L0.4 alias / codename display layer)

**Date:** 2026-06-17
**Parent brief:** `docs/codex-briefs/2026-06-17-L0-foundation-build-brief.md` §L0.4 (Titans-approved `3671c85`).
**Repo baseline:** `main` @ `d8c1522` (L0.1a shadow merged + deployed). Branch off current `main`. Worktrees in flight: `sb3-work`, `sec-work` — don't collide.
**Scope of THIS session:** L0.4 only — the alias/codename DISPLAY layer. Display-only (no signal-flow / scoring / DB-write change). No shadow window required, BUT a post-build Olympus committee pass IS required (committee agents see this).

---

## Purpose
Surface the strategy display names (Midas / Achilles / Hector / Apis / Kodiak / Triton / Nemesis / Icarus) consistently across every read surface, **additively** — the DB `signal_type` / `strategy` identifiers stay frozen so outcome history, the n-gates, CSS classes, filters, and any committee branching keep working. The whole risk here is *coverage*: a surface showing "GOLDEN_TOUCH" next to one showing "Midas" is worse than no alias. So the job is (a) one canonical map, (b) every presentation surface shows the codename, (c) raw values untouched everywhere.

## Pre-flight
1. `git fetch && git status` — clean, at `origin/main` (`d8c1522`).
2. New worktree/branch off `main`: `git worktree add C:\th-l0-alias -b l0-alias`. Do NOT use `th-scoring` / `th-security`.
3. Read `PROJECT_RULES.md`, parent brief §L0.4, and the master brief naming roster (`2026-06-16-rebuild-stack-master-brief.md` §11).

## Phase-0 (READ-ONLY — coverage audit + Olympus-safety check; no writes)
P0-1. **Frontend display chokepoints.** Read `formatSignalType()` and `formatStrategyName()` in `frontend/app.js` (+ `slugToLabel` in `analytics.js` / `laboratory.js`). Confirm they are the single display transform for `signal_type`/`strategy`. Inventory each call site as **DISPLAY** (alias) vs **LOGIC/CSS/FILTER** (leave raw) — e.g. `class="signal-card ${signal.signal_type}"` (CSS, raw), `strategy === enabled` (filter, raw), `if (signal.signal_type === 'APIS_CALL')` (logic, raw) must NOT be aliased.
P0-2. **MCP surface.** Read `backend/hub_mcp/tools/trade_ideas.py` — confirm it returns raw `signal_type`/`strategy`. This is the Olympus-facing surface; decide the additive `codename` field shape here.
P0-3. **Olympus-safety check (the important one).** Read the committee/PIVOT prompt builders (`scripts/pivot2_committee.py`, `pivot/llm/prompts.py`, and the VPS copy `scripts/vps_deploy/pythia_update/pivot2_committee.py`). Does ANY committee prompt/skill BRANCH on a raw `signal_type` string (conditional logic keyed on e.g. `GOLDEN_TOUCH`)? If yes → additive ONLY, never replace raw. Document what you find.
P0-4. **Notification surfaces.** Read `backend/discord_bridge/bot.py` + `scripts/signal_notifier.py` — how do they render `signal_type`/`strategy`? These need the codename too (or they drift from the UI).
P0-5. **Confirm the map** against the master brief roster. Multiple signal_types map to one codename (`SELL_RIP_EMA`/`VWAP`/`EARLY` → Achilles, via strategy `sell_the_rip`). Define precedence: signal_type-keyed first, then strategy-keyed, then raw fallback. L2 names (Triton→`Whale_Hunter`, Nemesis) — map them so it's ready; the fallback covers anything unmapped.

## Design (confirm/finalize in Phase-0, then build)
- **Single source of truth = Python.** `backend/config/strategy_aliases.py` holds the canonical map + `codename(signal_type, strategy) -> str` (raw fallback if unmapped).
- **Additive, never replacing.** Backend serialization boundary ADDS a `codename` field to signal responses (`feed_service.get_active_trade_ideas`, `hub_mcp/tools/trade_ideas.py`); `signal_type`/`strategy` stay as-is.
- **Frontend shows the field, doesn't duplicate the map.** Display helpers prefer `signal.codename` when present, else fall back to the existing `formatSignalType`/`formatStrategyName`. This avoids a second (drift-prone) JS copy of the map.
- **Non-response surfaces** (Discord, notifier, committee prompts) call the Python `codename()` directly — additively in prompts (include raw + codename) per P0-3.

## Tasks
1. **`backend/config/strategy_aliases.py`** — the map + `codename()` + precedence + raw fallback. Unit tests: each mapping, the multi-signal_type→Achilles case, unmapped→fallback, None-safety.
2. **Backend additive field** — add `codename` at the feed + MCP serialization boundary (P0-1/P0-2 anchors). Raw fields untouched.
3. **Frontend** — display helpers prefer `codename` with fallback. Do NOT touch raw-value CSS/filter/logic sites.
4. **Notification + committee surfaces** — apply `codename()` per P0-3/P0-4 (additive in prompts).
5. **Coverage check** — a grep/script confirming no presentation surface still shows a raw value where a codename exists.

## Gates / what NOT to do
- **ADDITIVE ONLY.** Never overwrite or mutate `signal_type` / `strategy`. Raw values are frozen (logic, CSS, filters, committee branching, outcome history all depend on them).
- **Display-only.** No signal-flow, scoring, or DB-schema/write change. No migration.
- **Do NOT alias raw-value logic sites** (CSS classes, filter matches, `if signal_type ==` branches). Only the display path.
- Deploy ONLY outside 7:30 AM–2:00 PM MT. Atomic commits, explicit pathspecs, **never `git add .`**, commit via `git commit -F C:\temp\commitmsg.txt`.

## Output spec
- `backend/config/strategy_aliases.py` + tests · the backend `codename` additions · the frontend helper change · the notification/committee surface changes · the coverage-check script. Commits in `feat(l0):` style on `l0-alias`. Do NOT merge to main without the coverage check + the Olympus committee pass below.

## Done definition
- Alias map + tests pass.
- Every identified read surface shows the codename consistently; raw `signal_type`/`strategy` untouched everywhere (verified by the coverage check).
- **Olympus Impact (REQUIRED):** run ONE full committee pass on a known-good ticker after the build, confirming agents reason correctly with codenames present and nothing keys on a now-masked raw string (TORO-fabrication-incident discipline). This is the gate for merge.

## Olympus Impact
YES — committee agents see codenames via the MCP tool + prompts. The additive design preserves raw values for any branching, so the risk is bounded; the post-build committee pass confirms it. No new MCP tool; no data-source change.
