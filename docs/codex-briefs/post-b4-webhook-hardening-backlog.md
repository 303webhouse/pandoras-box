# Post-B4 — Global Webhook-Hardening Backlog

**Opened:** 2026-06-09 (during B4 Chunk B) | **Status:** backlog, not scheduled
**Context:** B4 Chunk B hardened the PYTHIA path. Other inbound webhooks share the
same auth-bypass and fail-open patterns and should get a dedicated brief.

---

## #1 — FOOTPRINT dispatch bypasses the secret check (verified)

`backend/webhooks/tradingview.py:201-204` routes `signal == "FOOTPRINT"` payloads
to the footprint handler **before** the router's secret validation at lines 217-221
(the same early-return class that left the PYTHIA feed unauthenticated). The
FOOTPRINT branch forwards to `footprint_webhook(FootprintSignal(**payload))` with
no secret check → externally POST-able, unauthenticated.

**Fix pattern:** enforce a shared secret inside `footprint_webhook` (the chokepoint),
mirroring the B4 `pythia_webhook` hardening: constant-time compare, fail-closed,
required-field validation, secret-strip before persist.

---

## Other candidates to sweep in the global brief
- Audit **all** `/webhook/*` routers for the same pre-auth early-return pattern
  (`whale`, `footprint`, `hermes`, `circuit_breaker`, `mp_levels`, direct
  `/api/webhook/pythia`).
- The main `tradingview.py` secret check is **fail-open** (`if WEBHOOK_SECRET:` →
  skips when env unset) and uses a plain `!=` (not constant-time). Upgrade to
  fail-closed + `hmac.compare_digest` once the env var is confirmed set.
- Router-level raw-body size cap (B4 R-4 deferral) — apply once, centrally, at the
  `/webhook/tradingview` request read.
- Consider a single shared `validate_webhook_secret()` helper so every handler
  enforces identically instead of copy-pasted blocks.

---

*Logged from B4 Chunk B per PM rider 3. Promote to a full investigation-first
brief when scheduled.*

---

## Adjacent tickets (logged 2026-06-10, B4 close-out)

- **#2 — UW `/stock-state` retry-once before `unavailable`.** The quote/snapshot
  path returns `unavailable` on a single `/stock-state` blip. Add one retry
  (short backoff) before degrading — the endpoint is flaky under load (e.g. CPI
  days). Scope: `backend/integrations/uw_api.py`.
- **#3 — Chain provenance flag review.** Audit how `hub_get_options_chain` /
  marking surfaces `spot_source` / `greeks_source` / `uw_timestamp_source` so a
  `snapshot_fallback` or synthetic-timestamp read is never mistaken for a clean
  live mark.
- **#4 — Add a `version` field to PYTHIA Pine comFields.** `hub_get_market_profile`
  tags `source: "pythia_webhook_v2.4"` as a static string because the payload
  carries no version (verified 2026-06-10). Emitting `"version"` from the Pine
  would let the tool report true provenance instead of a hardcode.
