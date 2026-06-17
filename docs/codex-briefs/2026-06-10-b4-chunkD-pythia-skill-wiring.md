# B4 Chunk D — PYTHIA Skill Wiring + SPY Regression (GO-LIVE GATE)

**Date:** 2026-06-10 | **Author:** Architecture layer | **Builder:** CC (file edits) + Nick (upload + regression)
**GATE CONDITION:** Do NOT execute until the feed-restoration check passes at
the 2026-06-10 RTH open (events across many tickers, ideally fresh SPY events).
If the open shows 401s, fix the TV-side secret first; this brief waits.

**Target file:** `skills/pythia/SKILL.md` (repo copy). Five surgical edits with
exact anchors below, then package → upload → fresh-chat verify → regression.

---

## EDIT 1 — Insert the tool into PYTHIA's Context-A call order

**FIND** (the current items 2–4 of the numbered tool list):
```
2. `hub_get_bias_composite(timeframe="swing")` — directional bias context to cross-reference against the auction state read (e.g., "bias bullish + profile balanced + price at VAH = elevated fade risk into resistance")
3. `hub_get_flow_radar(ticker=<the ticker>)` — volume imprint / delta context at key MP levels; PYTHIA reads CVD and aggressor footprints at structural inflection points
4. `hub_get_positions(ticker=<the ticker>)` — existing exposure on this ticker (does Nick already have positions sitting at levels PYTHIA is about to flag?)
```

**REPLACE WITH:**
```
2. `hub_get_market_profile(ticker=<the ticker>)` — live Market Profile levels from the PYTHIA TradingView webhook feed: POC, VAH, VAL, prior-session value area (prev_poc/prev_vah/prev_val), IB high/low, poor high/low flags, VA migration, volume quality. Status semantics: `ok` = current-session levels (use as GROUND TRUTH with the `as_of` timestamp); `stale` = latest event is from a prior session — the levels are real prior structure, ALWAYS label them with `session_date`; `unavailable` = no data for this ticker — the data-caveat disclaimer fires. `single_prints` and `day_type` return null (not computed by Pine v2.4) — never infer them as data.
3. `hub_get_bias_composite(timeframe="swing")` — directional bias context to cross-reference against the auction state read (e.g., "bias bullish + profile balanced + price at VAH = elevated fade risk into resistance")
4. `hub_get_flow_radar(ticker=<the ticker>)` — volume imprint / delta context at key MP levels; PYTHIA reads CVD and aggressor footprints at structural inflection points
5. `hub_get_positions(ticker=<the ticker>)` — existing exposure on this ticker (does Nick already have positions sitting at levels PYTHIA is about to flag?)
```

---

## EDIT 2 — Rewrite the data caveat (the "MP data not provided" block)

**FIND** (entire block, verbatim):
```
Market Profile data (POC, VAH, VAL, IB, single prints, day type) is NOT currently available from either the hub or web_search. PYTHIA's structural reads rely on Nick providing the levels via screenshot, TradingView indicator, or verbal description. If Nick has not provided MP data, every PYTHIA output must explicitly state:

> "MP data not provided — analysis is auction-theory framework only, not session-specific levels."

**Closing the gap:** `hub_get_market_profile` is a v2 hub MCP candidate (via TradingView MP webhook → Railway pipeline) on the post-committee priority list. The four-phase plan to get there lives in `references/automation-roadmap.md`. Until that lands: framework reads only, no fabricated levels.
```

**REPLACE WITH:**
```
Market Profile levels (POC, VAH, VAL, prior-session VA, IB, poor highs/lows, VA migration) ARE now available live via `hub_get_market_profile` (B4, shipped 2026-06-10). Handling by tool status:

- **`ok`** — current-session levels. Use them as the LEVELS source of truth, anchored to the tool's `as_of` timestamp.
- **`stale`** — the latest event is from a prior session. The levels are genuine prior structure and remain usable (prior-day value areas matter), but EVERY reference to them must carry the `session_date` label so nobody mistakes them for today's auction.
- **`unavailable`** — no data exists for this ticker. The disclaimer fires, verbatim:

> "MP data not provided — analysis is auction-theory framework only, not session-specific levels."

**Still not in the feed:** `single_prints` and `day_type` return null (Pine v2.4 does not compute them). Day type MAY be classified qualitatively from price action and the available levels, but must be labeled as PYTHIA's inference, never as feed data. Single prints come only from Nick's screenshots. Nick-provided screenshots or levels always supplement the tool and win when fresher. Fabricating any level remains the cardinal sin (TORO-2026-05-21 precedent).
```

---

## EDIT 3 — Update the fabrication hard rule

**FIND:**
```
- Never fabricate Market Profile data. If POC, VAH, VAL, IB, single prints, or other levels are not provided by Nick or visible in a screenshot, state that explicitly and frame analysis qualitatively in auction-theory terms only.
```
**REPLACE WITH:**
```
- Never fabricate Market Profile data. If levels are not returned by `hub_get_market_profile` (status `ok` or labeled-`stale`), not provided by Nick, and not visible in a screenshot, state that explicitly and frame analysis qualitatively in auction-theory terms only.
```

---

## EDIT 4 — Update the LEVELS template sourcing note

**FIND:**
```
(Include only the levels Nick provided or that are visible in a shared screenshot. If none provided: "LEVELS: not provided — analysis is framework-only.")
```
**REPLACE WITH:**
```
(Sources, in priority order: `hub_get_market_profile` (`ok` = current session; `stale` = include but tag each level with its `session_date`), then Nick-provided levels/screenshots — fresher source wins. If the tool is `unavailable` AND Nick provided nothing: "LEVELS: not provided — analysis is framework-only.")
```

---

## EDIT 5 — Mark the automation roadmap as landed

**FIND:**
```
The MP data gap is closable via a TradingView → Railway webhook pipeline. See `references/automation-roadmap.md` for the four-phase plan (Phase 1: Key Level Alerts → Phase 4: Volume Delta Integration) and the training-value framing for Nick learning MP through implementation. The `hub_get_market_profile` v2 MCP tool is the eventual landing point.
```
**REPLACE WITH:**
```
The MP data pipeline LANDED 2026-06-10 (B4): TradingView Pine v2.4 → secured `/webhook/tradingview` router → `pythia_events` → `hub_get_market_profile`. See `references/automation-roadmap.md` for remaining phases (single prints, day-type classification, volume delta integration are still open — the tool returns null for fields the Pine doesn't compute yet).
```

---

## Packaging + upload (after the 5 edits)

1. CC: apply the edits, then run `scripts/package-skill.ps1 pythia` → produces
   `dist/skills/pythia.skill`.
2. CC: commit the SKILL.md change (explicit add, normal message rules).
3. Nick: re-upload to Claude.ai — **the FULL bundle including `references/`**,
   never SKILL.md alone (re-upload replaces the whole bundle).
4. Verify in a FRESH chat (uploaded skills don't refresh mid-session).

## The SPY regression (GO-LIVE GATE — from the approved Phase 1 brief)

Run in a fresh chat, during or after a session with confirmed fresh events:
1. Confirm SPY has a current-session `pythia_events` row (post-restoration).
   If SPY still isn't firing, run the regression on META instead.
2. Full Olympus committee pass on the chosen ticker. Pass criteria (ALL):
   - (a) PYTHIA calls `hub_get_market_profile` and populates LEVELS with the
     real POC/VAH/VAL when status is `ok`.
   - (b) On a quiet ticker (test separately), `stale`/`unavailable` produces
     labeled levels / the disclaimer — ZERO fabrication.
   - (c) TORO/URSA/PYTHAGORAS/THALES/DAEDALUS/PIVOT outputs unchanged in
     shape and lane discipline.
   - (d) No agent simulates another; PYTHIA stays structural.
3. Record results in
   `docs/strategy-reviews/b4-pythia-feed-closure-note-2026-06-10.md`.
   **No go-live without this note.** B4 closes when the note lands.
