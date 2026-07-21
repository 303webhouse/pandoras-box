# MICRO-BRIEF — DEF-FUNDING-CACHE-HEALTH

**Authored:** 2026-07-21, coordination lane
**Severity:** P1 — false-negative signal suppression with silent committee-input impact
**Origin:** DEF-FUNDING-DUTY-CYCLE Phase 0 (`04a1983`). That brief HALTED correctly; this is the real defect it surfaced.
**Type:** small code fix + verification. Config-free, recoverable, no migration, no schema change.
**Titans review:** not required — isolated bug fix per `TITANS_RULES.md § Review Workflow`. Recorded so the skip is deliberate.

---

## TASK 0 — FILING

```
cd /d C:\trading-hub
git fetch origin && git status
git mv 2026-07-21-def-funding-cache-health-micro-brief.md docs\codex-briefs\
git add docs/codex-briefs/2026-07-21-def-funding-cache-health-micro-brief.md
git commit -F C:\temp\commitmsg.txt
git push origin main
```

---

## THE DEFECT

`backend/bias_filters/coinalyze_client.py` caches the funding result at **line 119**, then attaches `health_status` at **line 120**. Ordering is inverted: the cached copy never carries the field.

Consequence chain:

1. First call inside the TTL window populates the cache and returns a dict **with** `health_status` → `degraded = false`.
2. Every subsequent call within the 300s TTL is a cache hit, returning a dict **without** `health_status`.
3. The funding consumer reads it with a bare `.get("health_status")` → `None`.
4. `None != "LIVE"` → **`degraded = true` on perfectly healthy data.**

**Funding is the only consumer using a bare `.get()`.** OI and basis pass a `"LIVE"` default and are structurally immune — which is why this presents as funding-specific rather than as a general client bug.

**Production repro (already established, `04a1983`):** three consecutive calls returned `degraded` = `false`, `true`, `true` with `rate_pct = 0.0013` **identical throughout**, OI and basis clean across all three.

### Why this is P1 and not cosmetic

D1.4 (`2eb079d`) correctly suppresses `FIRING → NEUTRAL` whenever the funding input reads degraded. That contract is right and stays. **It is being driven by a false input.** So genuine funding readings are suppressed on the read surface for the majority of calls, and both the Discord notifier and the committee **hide the funding line entirely** when it fires.

Name the class: this is **fake-degraded** — the mirror image of the fake-healthy rule in `PROJECT_RULES.md`. Fake-healthy is a confident wrong value. Fake-degraded is an honest contract suppressing a real signal on a false alarm. Same damage, opposite sign, and the existing rule would never have caught it. Its committee-input impact is the same class as the 7/2–7/15 stale-market-profile window: silent degradation of an input nobody knew was degraded.

### Sequencing note — this fix gates the persistence work

`degraded` is not persisted anywhere (Phase 0 verdict). **Do not instrument or persist it before this fix lands.** Doing so would durably record a cache artifact and manufacture a fake ~80–90% duty cycle in the historical record — creating a column with two incompatible regimes and no cutline marking the boundary. That is precisely the `signals.source` problem this project spent a full session resolving with the `id >= 15678` provenance cutline. Do not create a second one knowingly.

---

## PHASE 0 — CONFIRM BEFORE EDITING (short)

1. Read `coinalyze_client.py` lines ~110–130. Confirm the cache-write-then-attach ordering as described. **If the ordering is not as stated, this brief is wrong — report and stop.**
2. Confirm the funding consumer's bare `.get("health_status")` and the `"LIVE"`-default pattern used by OI and basis. Name file and line for each.
3. Confirm the TTL value (expected 300s) and identify every consumer of the cached funding entry — the fix must not change behavior for any other reader.

---

## PHASE 1 — FIX

**Primary (root cause): attach `health_status` before the cache write, not after.** The cached dict then carries whatever the real status was at fetch time — `LIVE` when live, `DEGRADED` when genuinely degraded. This preserves honest degradation rather than suppressing it, which a consumer-side default alone would not.

**Secondary (raise, do not silently bundle): the consumer inconsistency.** Aligning funding's bare `.get()` to the `"LIVE"`-default pattern used by OI and basis is defensible hardening and matches in-file precedent — but it also masks a missing field rather than fixing it, and bundling both changes makes it impossible to attribute the fix. **Report your recommendation with the Phase 0 findings; do not apply it in the same commit as the primary fix unless Nick or the coordination lane calls it.**

**Do not touch the D1.4 contract.** Suppressing `FIRING → NEUTRAL` on a genuinely degraded input is correct behavior and stays exactly as is. This brief fixes the input, never the rule.

---

## PHASE 2 — VERIFY

**The acceptance test already exists** — re-run the established failing repro.

1. **Unit:** a test proving a cache hit returns `health_status` intact. This test must **fail against the current code** — state that explicitly in the report. A regression guard that passes pre-fix guards nothing.
2. **Live, post-deploy:** three consecutive `/api/crypto/state/{symbol}` calls inside the 300s TTL. Pass = `degraded` **identical across all three** with an identical `rate_pct`. Prior failing state was `false, true, true` at `rate_pct 0.0013`.
3. **Non-regression:** confirm OI and basis still read clean across the same three calls — they were never affected and must stay unaffected.
4. **Honest-degradation proof:** confirm a genuinely degraded fetch still yields `degraded = true` on cache hits. The fix must not convert a real degradation into a false all-clear. **This is the one way the fix could be worse than the bug** — if it can only be reasoned about rather than exercised, say so plainly rather than claiming it.
5. Full suite. Bar is byte-identical known-red: **18 failed / 1 skipped / 200 errors**, passed rises by the new test count.
6. Four-step deploy verification. `/health=OK` is not proof.

---

## DONE DEFINITION

1. Phase 0 confirms the ordering, or reports a contradiction and stops.
2. Cache write carries `health_status`.
3. Consumer-alignment recommendation reported, **not applied**, absent an explicit call.
4. Regression test that demonstrably fails pre-fix.
5. Live three-call repro passes: identical `degraded`, identical `rate_pct`.
6. Honest-degradation path confirmed intact, or its unexercised status stated plainly.
7. Known-red byte-identical; four-step deploy verified.
8. `workstreams.md` STATER-SWAP row updated; DEF-FUNDING-DUTY-CYCLE marked CLOSED / not-measurable / superseded by this brief.

---

## OUT OF SCOPE

- Persisting `degraded` anywhere. Deferred indefinitely — the motivation (protecting two gate-flip decisions) evaporated when Phase 0 established neither gate reads this input.
- Flipping `funding_fade_negative_floor_raise_enabled` or the Tier-3 block. **Both stay shadow.**
- **`Funding_Rate_Fade`'s zero-signal problem.** Real, larger, and a different thread — routed to the silent-strategy triage (W2-4) alongside Kodiak, Nemesis, and Icarus. Do not investigate it here.

---

## OLYMPUS IMPACT

**Real, and the direction is worth stating.** Committee agents and the Discord notifier both hide the funding line when `degraded` fires. Post-fix, funding data will appear in crypto committee passes and embeds **substantially more often** than it does today.

That is a restoration, not a new feature — but it will look like a change in agent behavior, so it belongs in the closure note. Per the cross-reference rule, run **one crypto committee pass post-deploy** on a Tier-1 symbol (BTC or ETH) and confirm the funding line renders with sane values rather than the suppressed state that has been the norm.
