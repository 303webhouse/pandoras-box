# DEF-SIGNAL-METADATA — Phase 0 Findings

Date: 2026-07-21
Brief: `docs/codex-briefs/2026-07-21-def-signal-metadata-brief.md`
**Status: Phase 0 complete, reporting for a scope call before Phase 1+ — same discipline as every other brief-contradicting finding this program has surfaced.** Nick has been asked; escalating to Fable/Olympus per his instruction rather than deciding scope unilaterally.

## Verdict — what needs a call before proceeding

Two of the brief's three evidence points (S2, S3) **do not hold up** on investigation. The third (S1) is real and independently reconfirmed. This changes the brief's actual remaining scope substantially — from "fix a table-wide timestamp corruption + a compounding age-computation bug" down to "fix a cosmetic provenance column + optional hygiene hardening."

## S1 — `source` column is fiction, table-wide: **CONFIRMED, real**

`log_signal()`'s `INSERT INTO signals` (`backend/database/postgres_client.py:1638-1651`) never includes a `source` column. Independently reconfirmed this Phase 0: `SELECT DISTINCT source FROM signals` returns exactly one value, `'tradingview'`, for every row in the table regardless of true origin. `source` is unusable as a provenance signal anywhere in this table.

**One live side door found, worth folding into this brief's scope:** `POST /api/analytics/log-signal` (`backend/analytics/api.py:2072-2087`) calls `log_signal()` directly, bypassing `process_signal_unified()` entirely (skips scoring, feed-tier classification, gate evaluation, dedup, outcome-record writing, Discord/WS broadcast, committee flagging). It already self-tags `triggering_factors.bypass_source = "analytics_log_signal_endpoint"` in code (added `1e27d11`, 2026-06-18) — but a direct query shows **zero rows** carry that tag, meaning this endpoint is live/callable but has not actually been invoked since the tag was added. Not a live problem today; worth noting as a standing side door if the fix touches `log_signal()`'s call surface.

No SQL-level side door exists anywhere else — repo-wide grep for `INSERT INTO signals` found exactly one hit, inside `log_signal()` itself.

## S2 — `signals.created_at` runs ~6h hot: **FALSIFIED — was a viewing-tool artifact, not a bug**

This is a correction to two of my own earlier reports (`def-feed-triage-completion.md`'s V1 section, and the S-4 Phase 3 completion doc's addendum) — both have been annotated in place with this finding; not deleting the original wrong text, striking it through for the record.

**What's actually true:** `signals.timestamp` and `signals.created_at` are both `timestamp without time zone` columns (confirmed via `information_schema.columns`), and both **store correct UTC values**. `log_signal()`'s INSERT, `_normalize_timestamp_for_db()` (quoted and traced in full — correctly strips tzinfo from an aware datetime after converting to UTC, or passes a naive value through unchanged), the asyncpg connection pool (no timezone override, confirmed `SHOW timezone` → `Etc/UTC`), and every writer checked (crypto strategies, CVD engine, TradingView webhooks, CTA scanner) are all correct or at worst harmlessly naive-but-UTC-valued.

**What produced the appearance of a +6h bug:** `mcp__postgres__query` — the Postgres MCP tool used throughout this session — misparses `timestamp without time zone` values (Postgres OID 1114) when serializing them to its JSON response. It appears to construct a JS `Date` treating the naive wall-clock digits as **local time in America/Denver** (this machine/session's timezone, MDT = UTC−6 in summer), then calls `.toISOString()`, which always emits a UTC-labeled "Z" string — mechanically adding 6 hours in the process.

**Proof (reproduced live, apples-to-apples on the same row):**
| column | raw `::text` cast | JSON value via the same tool |
|---|---|---|
| `timestamp` | `2026-07-21 06:32:23.366271` (matches the signal_id-embedded epoch to the second) | `2026-07-21T12:32:23.366Z` — **+6h00m00.000s** |
| `created_at` | `2026-07-21 06:32:25.319999` (matches) | `2026-07-21T12:32:25.319Z` — **+6h00m00.000s** |

A sibling `timestamptz` column (`crypto_gate_shadow.evaluated_at`, on the identical row) reads correctly through the **same tool** in both forms — because it carries an explicit UTC offset the parser can't misinterpret. This isolates the bug precisely to the naive-timestamp type + this read client's default parser, not to anything about the row, table, or writer.

Re-checked the exact rows the original "confirmed" finding was based on (AMD/TFC/LYFT from `def-feed-triage-completion.md`'s V1 check) via raw `::text` casts: gaps of **4-58 seconds** between `timestamp` and `created_at` — normal processing latency, no 6-hour anomaly anywhere.

**One real, minor, separate hygiene finding along the way:** `backend/webhooks/tradingview.py` and `backend/scanners/cta_scanner.py` both have a naive `datetime.now().isoformat()` fallback (used only when an inbound payload doesn't supply its own timestamp) instead of `datetime.now(timezone.utc)`. This is currently harmless — correct only because Railway's container clock happens to be UTC — but fragile. Worth hardening for defense-in-depth, not because it's causing any observed problem today.

## S3 — `age_minutes` runs ~12h hot: **Compounding theory falsified; original 778-min sighting unexplained by any code defect found**

The brief's hypothesis was that S2's +6h write bug plus an independent +6h read-side computation bug would stack to ~12h. Since S2 doesn't exist, half the theory is already gone. But independently: `hub_get_trade_ideas`'s `age_minutes` computation (`backend/hub_mcp/tools/trade_ideas.py:44-59,163`, fed by `backend/signals/feed_service.py:185`) is **naive-to-naive arithmetic with zero additional timezone conversion** — it can only inherit whatever the DB column already holds, never independently double an error. And critically, the algebra runs the wrong direction: if `created_at` really were 6h *ahead* of true time (as originally, wrongly, claimed), `age_minutes = now − created_at` would come out **smaller** (or negative), not larger — it cannot produce +778 minutes from that direction of error.

The original 778-minute sighting (coordination-lane, 2026-07-20) remains unexplained by this investigation, but no code defect reproduces it. Most likely explanations, not yet confirmed: the flagged signal group's `newest_at` really was that old (a human/observer misjudgment of "should be ~50 min old"), or the observer's own tooling hit the identical naive-timestamp misparse artifact found above when displaying the raw `newest_at` field (which would corrupt the *displayed* freshness impression, not the separately-and-correctly-computed `age_minutes` number itself). Not investigated further per the scope question below.

## `log_signal()` caller inventory (brief task 1b)

Confirmed F-4's chokepoint is intact for every **automated** writer — scanners, webhooks, and scheduled scans all route through `process_signal_unified()`. The one exception is the `/log-signal` API side door noted under S1 above (live/callable, zero evidence of actual use).

**Unrelated finding surfaced along the way, not investigated further (flagging per standing discipline):** no `Crypto Scanner` strategy row has landed in `signals` since `2026-07-03` — 18 days, spanning the entire F-4 cutover (2026-07-15) — worth a look at whether `run_crypto_scan_scheduled()` is actually firing/finding qualifying signals post-cutover.

## Recommendation

Given S2/S3 aren't real, this brief's actual remaining scope is small: fix `source` passthrough (S1, real), optionally harden the two naive `datetime.now()` fallbacks (cheap, no urgency). No timestamp/age-computation code needs to change anywhere — nothing is broken there. Escalating this recommendation and the correction above to Fable/Olympus per Nick's instruction, rather than deciding to proceed with the reduced scope unilaterally.

## Constraints honored

Investigation-first, root cause in writing before any edit — no code changed in this Phase 0. Pathspec-only commit for this doc. No fixes applied pending the scope decision above.
