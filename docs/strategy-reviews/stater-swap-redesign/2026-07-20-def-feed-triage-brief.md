# DEF-FEED-TRIAGE — Crypto state feed integrity + notifier delivery

**Date:** 2026-07-20 (Monday), drafted ~08:40 MT
**Author:** Coordination lane (Fable), evidence gathered via VPS-side independent checks
**Priority:** P0-adjacent. **This brief PRECEDES S-4 Phase 3.** Phase 3's funding-fade gating must not be built against the current funding input (see D1).
**Repo HEAD at drafting:** `75fd853`
**Delivery note:** the coordination lane's local tooling (Desktop Commander) and GitHub write path are both down today, so this brief arrives as a file dropped at repo root. Task 0 moves it into place. GitHub main remains source of truth once you push.

---

## Task 0 — file into place (first commit of the session)

This file was dropped at repo root. `git mv` it to `docs/strategy-reviews/stater-swap-redesign/2026-07-20-def-feed-triage-brief.md`, pathspec-commit, push. Known repo quirk: there is a stray untracked file named `source` at root from a prior triage — **leave it alone**, it is separately queued for inspection.

## Phase -1 (mandatory, before any defect work)

1. `git fetch && git status` — confirm clean tree at or ahead of `75fd853` (plus this brief). Report any drift before proceeding.
2. Read `PROJECT_RULES.md`.
3. Investigation-first: each defect below gets read-only Phase 0 recon and a written root cause BEFORE any edit.

---

## Context

S-4 Phase 2 shipped and verified (see `s4-phase2-completion.md`). Monday-morning independent checks by the coordination lane found four defects in the surrounding plumbing. All evidence below was observed live and is quoted exactly — **re-verify each yourself in Phase 0** (curl the endpoint, read the logs) before trusting this document.

Diagnostic shape, one line each: **D1 = writer alive but emitting wrong values. D2 = writer has never written. D3 = writer stopped Saturday. D4 = delivery layer drops alerts under rate-limiting.**

---

## D1 — Funding feed emitting garbage; signal FIRES on degraded input (BLOCKS PHASE 3)

**Evidence (all UTC):**
- `GET /api/crypto/state/BTC` at 2026-07-20T14:05Z: `funding.rate_pct = 1.0`, `funding.signal = FIRING`, `funding.degraded = true`
- Same endpoint 2026-07-20T05:38Z: `rate_pct = 0.3286`, `FIRING`, `degraded = true`, funding `data_age` ~63s (writer is RUNNING — fresh timestamps, bad values)
- External cross-check 2026-07-20T~14:10Z, OKX public API `BTC-USDT-SWAP`: `fundingRate = 0.0000155` (= **0.00155% per 8h**). OKX's own venue cap is ±0.00375 (±0.375%/8h).
- If `rate_pct` means percent-per-8h, the hub is reporting ~**645x** the real market rate, and a value ~2.7x beyond a major venue's hard cap. A flat `1.0` with `degraded=true` smells like a clamp/sentinel/fallback or a ×100-class unit error — same family as the notifier unit bug killed pre-prod in Phase 2, but upstream in the writer path.

**Tasks:**
1. Phase 0: trace the write path for `funding.rate_pct` (coinalyze is the sanctioned primary per the capabilities block). Document the unit at every hop: vendor payload → writer → storage → API response.
2. Root-cause the `1.0` (clamp? default? fallback path? unit multiplication?). Write it down before fixing.
3. Fix units end-to-end so `rate_pct` is genuinely percent-per-8h from a real read.
4. **Contract change (small, in scope):** a signal must NOT report `FIRING` while its own input is `degraded=true`. Degraded input → signal suppressed/neutral, degradation surfaced. If implementing this touches a shared signal-emission path or any schema beyond the funding block, **STOP and flag for ATLAS** before proceeding.
5. Verify: live curl shows `rate_pct` in a sane band AND consistent with a same-hour external venue read. Record both numbers in the completion doc.
6. Post-fix sanity: with real funding near 0.0016%/8h vs the Phase 0.4 `abs_rate` floor of 0.0005 (0.05%), `funding.signal` should currently read QUIET, not FIRING. If it still fires after the fix, something is still wrong.

## D2 — Regime writer: zero rows, ever

**Evidence:** `regime.state = null`, note `"no regime rows yet"`, observed 2026-07-19T02:52Z, 2026-07-20T05:38Z, 2026-07-20T14:05Z. 35+ hour window on a 24/7 asset. Reader behavior is CORRECT (honest degradation) — do not touch the reader.

**Tasks:** locate the regime writer; determine whether it exists / is scheduled / is enabled / writes where the reader looks. Fix scheduling or enablement. Verify: rows appear, reader surfaces a real `regime.state`, and note the writer's intended cadence in the completion doc.

## D3 — CVD / tape_health collector frozen since Saturday

**Evidence:** `tape_health.as_of = 2026-07-18T17:23:15Z` across all reads; `data_age` 44.8h as of 2026-07-20T14:05Z. Collector stopped ~17:23Z Saturday.

**Tasks:** find why it stopped (crash? cron? upstream dependency? no supervisor?). Restart/fix. Verify fresh `as_of`. If there is no restart-resilience (nothing re-launches it on failure), note that as a follow-up item — do not build a supervisor in this session unless it is trivial.

## D4 — Equity notifier drops alerts on Discord 429, no retry

**Evidence:** `/var/log/signal_notifier.log`, run 2026-07-20T14:00:02Z: `signals_fetched 10, new_signals 10, alerts_posted 7`; three `[ERROR] Failed to post Discord alert ... HTTP Error 429: Too Many Requests` (AMD, LYFT, TFC). Those alerts are dropped permanently — logged and lost.

**Tasks:** in `signal_notifier.py` (shared by equity and `--crypto` modes — fix once, both benefit): add retry honoring Discord's `Retry-After` (or exponential backoff) plus inter-post spacing so a 10-alert burst doesn't trip the limit; ensure a failed alert is retried within the run or picked up by the next run rather than lost. Deploy via the proven byte-exact scp + sha-verify mechanism (see `def-notifier-stale-completion.md`). Verify: sha match on VPS + next multi-alert run posts clean.

## V1 — Bonus verify (~5 min): equity forensic flags, first live proof

The 14:00Z batch is the first natural equity signal set post-DEF-ENRICH. Query those 10 rows: confirm `needs_structural_review` / `iv_regime_extreme` / `vix_at_signal` persisted per spec. Note specifically whether AMD, LYFT, TFC (whose Discord posts failed) still persisted flags — persistence must be independent of notification success. Report in the completion doc. This closes the handoff's Monday verify (a).

---

## Constraints

- Investigation-first. Read-only Phase 0 per defect; written root cause before edits.
- Pathspec-only commits. No `git add .`.
- Backend deploys: full 4-step verify (Railway SUCCESS → exact SHA match → live curl of the changed surface → values real and non-degraded).
- VPS deploys: byte-exact scp + sha verify.
- No schema changes without an ATLAS flag. No scope creep into S-4 Phase 3 — **do not start Phase 3 in this session.**
- Fake-healthy is the P0 bug class: no fix may replace an honest degraded/null with a confident wrong value.

## Order and definition of done

**D1 → D2 → D3 → D4 → V1.** Done = all four defects root-caused in writing, fixed, deploy-verified per constraints; V1 findings recorded; completion doc at `docs/strategy-reviews/stater-swap-redesign/def-feed-triage-completion.md`; ledger updated in `docs/workstreams.md`. ACK to the coordination lane with the completion doc path.
