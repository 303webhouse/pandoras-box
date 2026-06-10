# Closure Note — B4: PYTHIA Market Profile Feed (`hub_get_market_profile`)

**Outcome:** SHIPPED — go-live gate CLEARED
**Date:** 2026-06-10
**Brief chain:** `docs/codex-briefs/2026-06-09-phase0-b4-pythia-market-profile.md` (Phase 0) → `docs/phase0-b4-findings.md` → `docs/codex-briefs/2026-06-09-phase1-b4-pythia-market-profile.md` (Phase 1) → Chunk runbook + this note.
**Master brief:** `docs/codex-briefs/2026-06-05-master-brief-edge-consolidation.md` §B4 — last item of sub-brief 2.

---

## What shipped (A → D)

| Chunk | What | Commit | Status |
|---|---|---|---|
| A | `hub_get_market_profile` — 13th hub MCP tool (read-only) | `52c0fcd` | deployed, verified |
| B | PYTHIA webhook hardening (constant-time secret, fail-closed, required-field/confident-zero validation, secret-strip, size cap) | `e351790` | deployed, cutover verified |
| C | Replay window (±10 min) + `(ticker,event,bar_time)` idempotency | `d61493b` | deployed, verified |
| D | PYTHIA SKILL.md wiring (5 edits) + bundle | `484fc59` | this push |

DAEDALUS-style note: ingestion + storage (`/webhook/tradingview` → `pythia_events`) already existed and ran live before B4 — the work was exposing it to the committee (the MCP tool), closing the unauthenticated write surface, and restoring the degraded feed.

---

## Feed-restoration evidence (2026-06-10 RTH open)

| Metric | Bug-era baseline | Post-v2.4 (since 09:30, ~2h in) |
|---|---|---|
| Distinct tickers | 3 (AMD, META, TSLA) | **190** |
| Events | 9–20 / day | **557** |
| Fresh SPY event | none since 2026-05-01 | **2** (regression ticker = SPY) |
| `/webhook/tradingview` 401s | — | **0** (all 200 OK in Railway logs) |
| `hub_get_market_profile("SPY")` | `stale` (2026-05-01) | **`ok`**, session 2026-06-10, POC 735.79 / VAH 738.38 / VAL 734.61 |

---

## SPY committee regression — 4/4 PASS (go-live gate)

Full Olympus committee pass on SPY (current-session feed, fresh chat with the re-uploaded bundle):

| # | Criterion | Result |
|---|---|---|
| a | PYTHIA calls `hub_get_market_profile` and populates LEVELS with real POC/VAH/VAL when status `ok` | ✅ |
| b | On `stale`/`unavailable`, labeled levels / disclaimer fire — **zero fabrication** (TORO-2026-05-21 precedent held) | ✅ |
| c | TORO/URSA/PYTHAGORAS/THALES/DAEDALUS/PIVOT outputs unchanged in shape + lane discipline | ✅ |
| d | No agent simulates another; PYTHIA stays structural | ✅ |

---

## Five observations of record

1. **Not greenfield — a read gap + an auth hole.** PYTHIA ingestion/storage was live (`pythia_events`, 9,666 rows at audit). The committee just couldn't read it, and the write surface was unauthenticated. B4 = MCP read + auth close + feed repair, not a new pipeline.
2. **The auth bypass was a dispatch-before-check ordering bug.** `/webhook/tradingview` early-returns `source=="pythia"` to `pythia_webhook` *before* its own secret check (`tradingview.py:207-213` vs `:217-221`). Fix had to live in `pythia_webhook` (the chokepoint serving both router-forward and direct hits) — a comFields secret alone would have done nothing. (FOOTPRINT shares this bypass — logged for the post-B4 webhook-hardening brief.)
3. **TradingView freezes script version at alert creation.** The degraded feed (3 tickers) was the live alert bound to pre-v2.4 code carrying the "watchlist tickers not calculated" bug. The delete+recreate re-arm rebound v2.4 → 190 tickers same session. Feed restoration was an expected, designed cutover outcome.
4. **Fail-loud discipline end-to-end.** Confident-zero `nz(x,0)` levels rejected at ingest (400); secret stripped before any log/persist (0 leaks table-wide); session-based staleness (`ok`/`stale`/`unavailable`) instead of a fake-healthy default; `single_prints`/`day_type` returned explicit `null` (Pine doesn't compute them) — no fabrication path anywhere.
5. **Verified, not asserted.** SPY flipped `stale → ok` post-restoration; idempotency (identical POST → one row + `duplicate`) and replay (30-min-old `bar_time` → 400) confirmed live with full residue cleanup; zero `/webhook/tradingview` 401s in production logs. Bundle `dist/skills/pythia.skill` (29.2 KB) re-uploaded; regression run in a fresh chat.

---

## Known-open (ticketed, not blocking)
- `single_prints` / `day_type` — not computed by Pine v2.4; tool returns `null`. Future Pine enhancement.
- No `version` field in the Pine comFields → `source` tag is a static `pythia_webhook_v2.4` (can't read true provenance from the payload). See post-B4 tickets.
- FOOTPRINT dispatch shares the pre-auth bypass — see `post-b4-webhook-hardening-backlog.md` #1.

**B4 CLOSES with this note on main.**
