# DEF-CVD-DIVERGENCE-LEAK — Findings + Remediation (P1)

**Lane:** BREACH (Chat 4), coordinated by Fable (spine). **Investigator:** Claude Code (Opus 4.8).
**Renamed from** DEF-CVD-SENTINEL-BREACH once the resurrection hypothesis was killed.
**Permanent record:** *"0 lifetime fires ≠ cannot fire."*

---

## 1. Root cause (reconstruction — graded EXEMPLARY, resurrection hypothesis DEAD)

A fresh `CVD_DIVERGENCE` row (`id=16160`, `CRYPTO_CVD_CVD_DIVERGENCE_BTC_VAL_1784883683506`,
BTC/LONG, `2026-07-24T09:01:21Z`, score 9) surfaced from a detector believed dark. It was **not** a
seed/startup resurrection. Two independent facts killed that hypothesis:

1. **`crypto_cycle_config` was never resurrected.** Max `id=5` (the DEF-CVD-QUARANTINE sentinel,
   `absorption_cvd_threshold_usd=1e15`) is still the top row; **no `id=6`** appeared at any of the
   four restarts. The startup seed ([postgres_client.py:1329](../../backend/database/postgres_client.py#L1329))
   is **already empty-table-guarded** (`if not existing_cycle_config:`) — the `2cddf49` pattern was
   already present. The only other two INSERT sites are manual one-shot scripts, never run at boot.
2. **The sentinel never gated the divergence branch.** Option A only raised the *absorption*
   threshold; the quarantine brief recorded **0 CVD_DIVERGENCE lifetime** and relied on the branch
   being *"mathematically dead."* There was nothing to re-enable.

**The detector code was unchanged and deployed** (`git diff origin/main` empty; last change
`e14a8bd`, 2026-07-21). The 05:30Z S-6 deploy touched only frontend + docs. The four restarts are
**coincidental, not causal.**

**What actually fired it:** standing code at
[crypto_tape_health_engine.py:293](../../backend/bias_filters/crypto_tape_health_engine.py#L293)
(`is_local_low and cvd_net > 0`). The "mathematically dead" claim was wrong: `is_local_low` requires
`close == own_low == window_min_low` — **rare, not impossible** (`0/272` was near-zero probability).
Most likely it became reachable once the `5da9e6c` source-sort made `recent[-1]` the true latest
bar. `event_reason`: *"price new local low near VAL but net CVD buying ($2,175,265)"* — a genuine
evaluation of a phantom structure, then graded BAR_WALK → LOSS. It was **visible** because the Tier A
filter excludes only rows carrying the `quarantine` key (the frozen 349-row set); a brand-new row
carries none.

## 2. Timeline (UTC → MT, MDT = UTC−6)

| UTC | MT | Event |
|-----|----|-------|
| 07-23 05:06:29Z | 07-22 23:06 MDT | config `id=5` sentinel — absorption killed |
| 07-23 15:23–15:45Z | 09:23–09:45 MDT | Tier A quarantine marker + deploy `ccfbffb` → historical CVD dark |
| 07-24 00:21 / ~02:00 / ~02:30 / ~05:30Z | 07-23 18:21 → 23:28 MDT | four restarts (reconciliation ×3, S-6 deploy) — detector untouched |
| 07-24 09:01:21Z | 03:01 MDT | **CVD_DIVERGENCE_BTC_VAL fired** (LONG, score 9, cvd_net +$2.175M) |
| 07-24 09:33:37Z | 03:33 MDT | graded BAR_WALK → LOSS |
| 07-24 18:53Z | 12:53 MDT | Step 1 quarantine written |

## 3. Fable ruling (spine → BREACH lane)

Findings EXEMPLARY; step-2 gate did its job (refusing a wrong fix is why it exists). Execute in
order: (1) full Tier A quarantine on `id=16160` — Nick's `--i-have-go`; (2) config-gated,
fail-closed source-kill of the divergence branch; (3) findings doc to `docs/codex-briefs` on main via
the clean-worktree method; (4) HOLD deploy for "AEGIS deploys complete," then deploy + four-step
verify + one controlled restart. §5d.1 redesign stays post-vacation, unchanged.

---

## 4. Remediation executed

### Step 1 — ROW quarantine ✅ (Nick's `--i-have-go`)
- Additive `enrichment_data.quarantine = {reason: DEF-CVD-DIVERGENCE-LEAK, class: phantom_divergence,
  at, brief}` on `id=16160`, **merge-not-reconstruct** (clobber-safe), `signal_id` untouched.
- **Pre-image (2 rows: signals + signal_outcomes) to BOTH locations** before the write:
  `backend/database/archive/def_cvd_divergence_leak_preimage_20260724T185329Z.jsonl` + `C:\temp\…`.
- Verified in-transaction: 1 row affected; all 4 original enrichment keys preserved; outcome/status/
  prices unchanged; CVD row-count invariant **350==350**; quarantined **349→350**.
- Post-write: **0 CVD rows pass the feed predicate** (`enrichment_data->'quarantine' IS NULL`).
- Reversal = strip the `quarantine` key; pre-image JSONL is the full-restore backstop.

### Step 2 — SOURCE-KILL ✅ (branch `def-cvd-divergence-leak`, cut from origin/main)
- [crypto_tape_health_engine.py](../../backend/bias_filters/crypto_tape_health_engine.py): both
  `CVD_DIVERGENCE` branches gated on `divergence_enabled = bool(cvd_cfg.get("divergence_enabled",
  False))` — **fail-closed at the origin** (missing key / stale / failed config load → OFF). No rows
  written, no junk accumulation. Absorption is untouched (its `not is_local_high and not is_local_low`
  condition is unchanged). The live sentinel config (id=5) has no such key → divergence is OFF on
  deploy with **no config write required**.
- [crypto_cycle_config_seed.py](../../backend/config/crypto_cycle_config_seed.py): documented
  `divergence_enabled: False` default for future re-seeds.
- Tests: existing divergence-detection tests opt into `divergence_enabled: True` (logic intact); 3 new
  fail-closed regressions added. **26 passed** (`py_compile` clean).

### Step 3 — Findings doc ✅
- This file, filed via the clean worktree (not the parked s6 checkout), same commit series as Step 2.

### Step 4 — DEPLOY ⏸ HELD for Fable "AEGIS deploys complete" (S5 in flight)
- On the signal: push branch → main (Railway auto-deploy) → four-step verify → **one controlled
  restart proving the branch stays dark** → confirm feed 0 CVD rows + outcome excluded. SHA appended
  below on completion.

---

## 5. Out of scope / deferred
- **§5d.1 detector redesign** (compare current bar high/low vs the *prior* window; fix tautological
  proximity): **post-vacation, unchanged.** Until then, divergence stays config-OFF.
- **edge/Triton raw-path stats:** same Tier B (SIGNALS-READ-LAYER) gap that already applies to the
  349 historical rows — the deployed Tier A filters (feed_service, score_signals, outcome_resolver)
  exclude this row on the committee surface; the ~10 raw read paths remain Tier B.

## 6. Deploy record (appended at Step 4)
- _PENDING — awaiting "AEGIS deploys complete."_
