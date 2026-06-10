# Phase 0 Brief — B4: PYTHIA Market Profile Feed (`hub_get_market_profile`)

**Date:** 2026-06-09 | **Author:** Architecture layer (Claude.ai) | **Builder:** Claude Code
**Mode:** READ-ONLY INVESTIGATION. No code changes, no schema changes, no migrations, no deploys.
**Gate:** Produce `docs/phase0-b4-findings.md`, then STOP and wait for review.

---

## Context

PYTHIA (Olympus committee Market Profile specialist) currently has no live structural
data feed. B4 closes that gap: a TradingView webhook pushes market-profile levels
(POC, VAH, VAL, IB, day type, etc.) computed by `docs/pythia-market-profile-v2.3.pine`
into the hub, stored in Postgres, and exposed as a 10th Hub MCP tool,
`hub_get_market_profile`.

This is the last item in sub-brief 2 of the edge-consolidation master brief
(`docs/codex-briefs/2026-06-05-master-brief-edge-consolidation.md`).

**Olympus Impact rule applies:** anything feeding PYTHIA requires a full committee
regression pass on a known-good ticker before go-live. Phase 0 must define that
regression plan, not just the build.

---

## Hard rules for this phase

1. Read-only. `git fetch && git status` first (from `C:\trading-hub`, via cmd).
2. No writes to prod DB. If you need to inspect prod schema, use read-only queries
   via the `railway run` + `trolley.proxy.rlwy.net:25012` / `ssl.CERT_NONE` pattern.
3. Verify against live data, not specs. (UW api_spec precedent: real field names
   differed from documented ones. Apply the same skepticism to TradingView docs.)
4. Fake-healthy states are failures. Any design that returns a confident default
   on missing data gets flagged, not shipped.
5. STOP at the gate report. Nick greenlights the build brief separately.

---

## Investigation tasks

### T1 — Pine script audit
Read `docs/pythia-market-profile-v2.3.pine` end to end. Document:
- Every value it computes (POC, VAH, VAL, IB high/low, day type, single prints,
  poor highs/lows, value-area migration, anything else).
- What an `alert()` payload from this script would/could contain. Does the script
  already build an alert JSON, or does that need to be added (note: adding it is
  Phase 1 work — just spec it here)?
- Expected alert cadence (per bar close? session events only?) and which
  tickers/timeframes it runs on.

### T2 — Existing inbound-webhook surface
Search `backend/` for any existing externally-POSTable FastAPI routes (webhooks,
alert receivers, TradingView ingestion). Document:
- How TradingView data currently enters the system, if at all.
- Whether an inbound-webhook pattern already exists to reuse (auth, validation,
  logging), or whether B4 introduces the hub's FIRST external write surface.
  If it's the first, say so loudly — it changes the AEGIS risk profile.

### T3 — PYTHIA data contract
From the PYTHIA skill's documented needs (POC, VAH, VAL, value area, IB,
single prints, poor highs/lows, day-type classification, prior-session values,
80% rule inputs), define the exact response shape `hub_get_market_profile`
must return. Follow the existing hub response conventions:
`status` / `data` / `staleness_seconds` / `schema_version` / `error`.

### T4 — MCP tool registration pattern
Locate where the existing 9 `hub_get_*` tools are registered (FastMCP 3.3.1).
Document file paths, the registration pattern, and exactly what a 10th tool
requires. Note anything that would force a hub restart pattern beyond the
normal 60–170s deploy window.

### T5 — Storage design (propose, do not run)
Draft DDL for a snapshot table (working name `market_profile_snapshots`):
columns, indexes, retention policy, and the read pattern. Apply the GEX lesson:
if reads should be latest-row-only, design the query and staleness guard that
way from day one. Migration number would be next in sequence — draft only.

### T6 — Security design (AEGIS lane — this is the heart of Phase 0)
TradingView webhooks cannot send custom HTTP headers, which constrains auth
options. Verify current TV capabilities against their live docs, then evaluate:
1. **Shared secret in the JSON payload** (e.g. `"secret": "..."`), compared
   server-side with a constant-time comparison. Secret lives in a Railway env
   var (working name `PYTHIA_WEBHOOK_SECRET`) — never in the repo, never logged.
2. **HMAC over the body** — only if TV alert templating can actually produce
   one; verify, don't assume.
3. **TradingView IP allowlist** as defense-in-depth (TV publishes webhook
   source IPs — confirm the current list and whether Railway can enforce it,
   or whether it must be app-level).
Also spec: replay protection (timestamp tolerance window), payload size cap,
rate limiting, and logging hygiene (payloads logged WITHOUT the secret field).
Malformed or unauthenticated payloads must fail loud: rejected + logged,
never silently coerced into a row.

### T7 — Failure modes & staleness
Define behavior for: TV alerts stop arriving (staleness threshold + flag),
market closed (expected freeze, mirror the composite's off-hours behavior),
partial payloads (reject whole payload, no partial inserts), and duplicate
alert delivery (idempotency key).

### T8 — Olympus impact map & regression plan
List every committee artifact that references market-profile data. Define the
post-build regression: full committee pass on a known-good ticker (suggest SPY),
comparing PYTHIA's output with the feed live vs. her current no-feed baseline.
This regression is a GO-LIVE GATE, not optional.

---

## Gate report — required output

Write `docs/phase0-b4-findings.md` with these sections:
1. Webhook surface inventory (T2) — including the "first external write
   surface?" verdict.
2. Pine payload spec (T1).
3. `hub_get_market_profile` data contract (T3).
4. Proposed schema + draft DDL, NOT executed (T5).
5. Security design with an AEGIS-style checklist (T6).
6. Failure-mode table (T7).
7. Olympus impact map + regression plan (T8).
8. Open questions for Nick / architecture layer.
9. Recommended Phase 1 build chunks, smallest-first, each independently
   shippable in shadow.

Then **STOP**. No code, no schema, no deploys until the gate is reviewed in
chat and Nick relays the greenlight.
