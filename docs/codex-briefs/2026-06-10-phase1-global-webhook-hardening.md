# Phase 1 — Global Webhook Hardening (build brief)

**Opened:** 2026-06-10 · **Source census:** `docs/phase0-global-webhook-hardening-findings.md`
**Lane:** security only. Do **NOT** modify scoring/signal/enrichment *logic* — gates live in the
webhook handlers (`backend/webhooks/`) + one shared helper in `backend/utils/`.
**Prime fact:** `TRADINGVIEW_WEBHOOK_SECRET` is **NOT set in Railway** → six endpoints
(`tradingview`, `breadth`, `tick`, `mcclellan`, `whale`, `footprint`) are **live-unauthenticated**.

---

## The one rule that governs every chunk

**Re-arm before flip. Set the env var during the chunk's own cutover — never preemptively.**

Per-chunk cutover order (do not reorder):
1. **Re-arm** the alert(s) for that chunk to send `secret` in the payload (Pine edit or TV
   message-box edit — see re-arm class per chunk).
2. **Deploy** the handler change in **observe mode**: validate the secret but log-and-allow on
   mismatch (so a missed re-arm doesn't drop a real signal). Confirm logs show the secret arriving.
3. **Set the env var** (`TRADINGVIEW_WEBHOOK_SECRET`, or the chunk's secret) in Railway.
4. **Flip fail-closed**: remove observe-mode allow; mismatch/absent → 401, unset env → 503.
5. Verify the live feed still lands; verify a secretless POST now 401s.

A preemptive env set would 503 every still-unarmed endpoint simultaneously — that is the failure
mode this rule exists to prevent.

---

## Chunk 0 — Shared helper (foundation, no re-arm, no cutover)

Create `backend/utils/webhook_auth.py`:

```python
def validate_webhook_secret(supplied: str | None, *, secret: str, observe: bool = False) -> None:
    """Fail-closed, constant-time webhook secret check.
    - secret == "" (env unset)      -> 503 (unless observe)
    - mismatch                      -> 401 (unless observe)
    - observe=True                  -> never raise; caller logs the verdict
    """
```

- Use `hmac.compare_digest`. Mirror the AEGIS blocks already in `mp_levels.py` /
  `pythia_events.py` (size cap + secret-strip helpers can live here too).
- Add `enforce_size_cap(request_or_payload, max_bytes=8192)` and `strip_secret(payload)` helpers
  so every handler is one-liner identical instead of copy-paste.
- Pure addition. Ship first; everything below calls it.

---

## Severity-ordered chunks (Olympus-feeding first)

> Each chunk = code change + re-arm + staged cutover (the one rule above). Estimated risk is
> "how much live Olympus input goes dark if cutover is fumbled."

### Chunk A — Footprint (lowest risk; do first) · committee-confluence input
- **Code:** replace footprint.py:219-224 (fail-open `!=`) with the shared helper; add size cap +
  secret-strip. Tighten the TV-router FOOTPRINT dispatch (tradingview.py:201-205) so the forwarded
  path can't regress past the gate.
- **Re-arm class:** **none.** `trojan_horse_footprint_v2.pine:84` **already sends** `webhookSecret`.
- **Cutover:** observe → confirm secret present → set env → flip. Trivial because the alert is
  already armed; this is the safe canary that also sets `TRADINGVIEW_WEBHOOK_SECRET` for the
  shared-secret family.

### Chunk B — Whale · committee-confluence input
- **Code:** whale.py:254-259 → shared helper + size cap + strip.
- **Re-arm class:** Pine-alert(). `whale_hunter_v2.pine` is 🟡 *not wired to TV* per inventory →
  near-zero live traffic; add `input.string` secret + concat into the alert JSON now so it's armed
  when the alert is eventually configured.
- **Cutover (RIDER 2 — do NOT flip this sprint):** add the secret to the Pine now, but leave the
  server gate in **OBSERVE mode through sprint end**. The alert is dormant, so flipping the endpoint
  to 503 now is a future-surprise (a forgotten dormant 503 when someone finally wires the alert).
  It goes **fail-closed later, in the same motion as wiring its live alert** — not here. Reuses
  `TRADINGVIEW_WEBHOOK_SECRET` (set in A).

### Chunk C — TV-router core + strategy fan-out (largest blast radius) · strategy signals
- **Code:** tradingview.py:217-221 → shared helper (fail-closed + constant-time). Ensure the gate
  also covers the FOOTPRINT (→A) and PYTHIA (already AEGIS) early-returns — i.e. no strategy path
  can reach the pipeline unauthenticated.
- **Re-arm class:** Pine-alert(), **multiple scripts.** Add the secret to every live strategy that
  posts to `/webhook/tradingview`: **Artemis** (`artemis_v3.pine:358/364`), Holy Grail
  (`holy_grail_webhook_v1.pine`), Scout (`scout_sniper_v3.1.pine`), Hub Sniper
  (`hub_sniper_v2.1.pine`), Phalanx (`phalanx_v2.pine`).
- **Cutover:** highest care. Stage in observe mode and watch logs until **all** strategy families
  show the secret, then flip.
- **RIDER 1 — coordination protocol (`tradingview.py` is shared with the scoring session):**
  1. **The scoring session lands its `tradingview.py` changes FIRST.**
  2. **This (security) session rebases onto those changes before editing `tradingview.py`** — do
     not start Chunk C on a stale `tradingview.py`.
  3. **Chunk C's router-gate flip is sequenced AFTER the scoring session's regime work in that file
     settles.** The fail-closed flip must not collide with their in-flight pipeline/regime edits.
  Treat this ordering as a hard dependency, not a suggestion.

### Chunk D — Bias-factor webhooks (tick / breadth / mcclellan) · bias factors
- **Code:** add the shared helper to `/webhook/tick` (1032-1035), `/webhook/breadth` (975-978),
  `/webhook/mcclellan` (1099-1102) in tradingview.py. Gate is in the handler; the factor-scoring
  modules it calls stay untouched (read-only for this sprint).
- **Re-arm class:** Pine-alert(), 3 scripts (`tick_reporter.pine`, `breadth_webhook.pine`,
  `mcclellan_webhook.pine`) — dynamic `alert()` builds, add `input.string` secret + concat.
- **Cutover:** these move the **composite bias**, so an unauth POST is a bias-spoofing vector —
  worth closing. Reuses `TRADINGVIEW_WEBHOOK_SECRET`. Re-arm 3, observe, set (already set by A),
  flip per endpoint.

### Chunk E — Hermes (harden all 9, no trim) · highest unauth-write impact
- **Justification:** the **VPS-scrape-burst lever** (`vps_trigger_url` → 188.245.250.2:8000) is a
  resource-abuse / amplification risk. (Catalyst-card writes are *not* the rationale.)
- **Code:** add a secret (or reuse `require_api_key`-style key) gate to `/api/webhook/hermes`
  (hermes.py:76, currently field-validate only). Match auth on the
  `/api/hermes/alerts/{event_id}/dismiss` PATCH (hermes.py:423) so a state mutation isn't open.
  Consider a Hermes-specific secret env (e.g. `HERMES_WEBHOOK_SECRET`) so its cutover is isolated
  from the TV family.
- **Re-arm class:** **Message-box ×9** (no Pine in repo — JSON hand-authored in TV UI). Edit the
  *Message* field of all 9 ticker alerts to add `"secret":"…"`. 9× human-error surface → re-arm in
  observe mode, confirm all 9 in logs, then flip.
- **Cutover:** isolated env var; flip only after all 9 confirmed.

### Chunk F — Circuit Breaker (add the cheap secret) · bias-state writer
- **Code:** add shared-secret validation to `/webhook/circuit_breaker` (circuit_breaker.py:590,
  currently intentional-public). Update the "intentionally public" docstring to reflect the new gate.
- **Re-arm class:** Pine-alert() **static literal** — `circuit_breaker_spy.pine` /
  `circuit_breaker_vix.pine` use a fixed JSON string; add `"secret":"…"` to the 4+2 literals.
- **Cutover:** closes the unauth `bias_cap`/`bias_floor`/`scoring_modifier` write (scoring-DoS
  vector). Low traffic (fires on state change only).

### Chunk G — Cleanup (**slack-cutter — drop first if timeline tightens**) · pure-QoL
- Remove or gate `/webhook/test` (tradingview.py:1222, open echo + log-injection surface).
- Decide whether `/webhook/outcomes/{signal_id}` (tradingview.py:1192) needs auth (low — read-only,
  id-guess required).
- Apply the **R-4 router-level raw-body size cap** centrally at the `/webhook/tradingview` request
  read (AEGIS endpoints already cap per-handler).
- *Explicitly deprioritized per Nick. If the sprint runs hot, ship A–F and defer G.*

---

## Definition of done (per chunk)

- [ ] Handler uses `validate_webhook_secret` (fail-closed, constant-time) + size cap + secret-strip.
- [ ] Alert(s) re-armed and **observed** sending the secret in Railway logs.
- [ ] **RIDER 3 — observe-mode exit condition:** **N consecutive valid secret-bearing POSTs across
      ALL alerts in the chunk** before the fail-closed flip. No flip on a vibe.
      - Hermes (Chunk E): **all 9 tickers** seen with a valid secret.
      - Bias factors (Chunk D): **all 3 feeds** (tick, breadth, mcclellan) seen.
      - Strategies (Chunk C): all live strategy families seen.
      - Suggested N = 3 consecutive clean POSTs per alert (raise for low-frequency feeds).
- [ ] Env var set **during this chunk's cutover** (not before).
- [ ] Fail-closed flip deployed; a secretless POST returns 401, unset env returns 503.
      *(Exception — Chunk B: stays observe-mode through sprint end per Rider 2; no flip.)*
- [ ] Live feed verified still landing post-flip.
- [ ] `py_compile` clean before deploy; push to main (Railway auto-deploys) → `/health` check.

## Sequence summary

`Chunk 0` → `A (footprint, sets TV secret)` → `B (whale)` → `C (TV-router + strategies, coordinate)`
→ `D (bias factors)` → `E (hermes ×9, own secret)` → `F (circuit breaker)` → `G (cleanup, droppable)`.

## Out of scope (this sprint)
- Any scoring/signal/enrichment **logic** change.
- The Hermes data-flow audit (catalyst_events vs `hub_get_hermes_alerts` calendar decoupling,
  committee wiring, UI surfacing) — captured as raw observations in §6 of the census; a dedicated
  Hermes-audit Phase 0 owns it.
