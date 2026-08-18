# ORPH — RESULTS (RE-RUN) · executed 2026-08-18 ~02:32Z (2026-08-17 20:32 MDT)
Executor: CC-SHELL. SELECT-only, VERBATIM from the ORPH spec held in session record.

**PROVENANCE — RE-RUN, NOT A RESCUE.** The 2026-08-03 ORPH-RESULTS.md did not survive:
scratchpad `f6bb84d7-…` is an empty tree, and the CC-SHELL scratchpad retains only the two
RH-reconciliation scripts. Spec re-executed verbatim. Where this run differs from the
2026-08-03 figures, the delta is real drift and is called out below.

**Transport note (§0 R1):** `mo` and `d` are MCP-rendered through the Denver lens; the
underlying values are in-DB (`DATE_TRUNC`, `::date`) and correct.

Rowcounts: ORPH-1a = 30 · ORPH-1c = 15 · ORPH-2a = 1 · ORPH-2b = 1

---

## HEADLINE — the orphan mechanism is STILL LIVE

| | 2026-08-03 | 2026-08-18 | delta |
|---|---|---|---|
| orphans | 369 | **370** | **+1** |
| with stem twin | 134 | 134 | 0 |
| UUID-keyed | 61 | 61 | 0 |

The 2026-08-03 run concluded "latest orphan is 2026-07-27; none in August." That is no longer
true. A new orphan was written **2026-08-10**: `ARTEMIS_CBRE_20260810_033744_132427`
(STOPPED_OUT). Orphan production is not a closed historical artifact — it is an active writer
defect. The new row falls in the "neither" class (no stem twin, not a UUID), which grows
174 -> 175.

## ORPH-1a — orphan population, temporal x type · 30 rows

| mo | signal_type | n |
|---|---|---|
| 2026-03 | ARTEMIS_LONG | 1 |
| 2026-03 | ARTEMIS_SHORT | 5 |
| 2026-03 | BULL_WALL | 1 |
| 2026-03 | FOOTPRINT_SHORT | 1 |
| 2026-03 | HOLY_GRAIL_1H | 48 |
| 2026-03 | MANUAL_LONG | 1 |
| 2026-03 | PHALANX_BEAR | 1 |
| 2026-03 | PHALANX_BULL | 2 |
| 2026-03 | SELL_RIP_EARLY | 11 |
| 2026-03 | SELL_RIP_EMA | 53 |
| 2026-03 | SELL_RIP_VWAP | 14 |
| 2026-03 | Session_Sweep | 3 |
| 2026-06 | ARTEMIS_LONG | 9 |
| 2026-06 | ARTEMIS_SHORT | 7 |
| 2026-06 | FOOTPRINT_LONG | 1 |
| 2026-06 | FOOTPRINT_SHORT | 3 |
| 2026-06 | HOLY_GRAIL_1H | 53 |
| 2026-06 | PULLBACK_ENTRY | 40 |
| 2026-06 | RESISTANCE_REJECTION | 2 |
| 2026-06 | SELL_RIP_EMA | 2 |
| 2026-06 | Session_Sweep | 11 |
| 2026-07 | ARTEMIS_LONG | 8 |
| 2026-07 | ARTEMIS_SHORT | 1 |
| 2026-07 | FOOTPRINT_SHORT | 1 |
| 2026-07 | HOLY_GRAIL_1H | 49 |
| 2026-07 | PULLBACK_ENTRY | 19 |
| 2026-07 | SELL_RIP_EMA | 4 |
| 2026-07 | SELL_RIP_VWAP | 3 |
| 2026-07 | TWO_CLOSE_VOLUME | 15 |
| **2026-08** | **ARTEMIS_LONG** | **1** |

Month totals: 2026-03 = 141 · 2026-06 = 128 · 2026-07 = 100 · **2026-08 = 1** · sum = 370.
**2026-02, 2026-04 and 2026-05 contribute zero.** The gap-then-resume pattern persists, now
with a fourth era opening in August.

Seven `signal_type` values still have no counterpart in the §1 roster: `BULL_WALL`,
`PHALANX_BEAR`, `PHALANX_BULL`, `MANUAL_LONG`, `PULLBACK_ENTRY` (59), `RESISTANCE_REJECTION`,
`TWO_CLOSE_VOLUME` (15). `signal_outcomes.signal_type` remains un-rosetta'd against
`signals.strategy`.

## ORPH-1b — earliest era

Not re-run: superseded by ORPH-1a's temporal breakdown plus the 2026-08-03 record (earliest
orphan `TEST_MANUAL_123`, 2026-03-06, EXPIRED; then WALL_SPY / PHALANX_* on 03-11; then the
HG_* block on 03-17). Re-running ORDER BY created_at ASC would return the identical rows, as
no orphan predating 2026-03-06 can be created retroactively. Flagged so the omission is on the
record rather than silent.

## ORPH-1c — raw key sample, latest era · 15 rows

| signal_id | d | outcome |
|---|---|---|
| **ARTEMIS_CBRE_20260810_033744_132427** | **2026-08-10** | **STOPPED_OUT** |
| ARTEMIS_AVGO_20260727_145800_607745 | 2026-07-27 | STOPPED_OUT |
| ARTEMIS_MDLZ_20260727_145721_682055 | 2026-07-27 | STOPPED_OUT |
| ARTEMIS_AMC_20260727_145716_744266 | 2026-07-27 | HIT_T2 |
| ARTEMIS_FCX_20260727_145107_918815 | 2026-07-27 | STOPPED_OUT |
| HG_URA_20260727_144927_rsi | 2026-07-27 | HIT_T1 |
| HG_FXY_20260727_144926_rsi | 2026-07-27 | STOPPED_OUT |
| HG_XLU_20260727_144919_rsi | 2026-07-27 | STOPPED_OUT |
| HG_XLY_20260727_144917_rsi | 2026-07-27 | STOPPED_OUT |
| b49a4524-ee65-4004-8704-6ef1376624fb | 2026-07-27 | STOPPED_OUT |
| 0d7e8f72-77a6-466f-aae1-f35f79298480 | 2026-07-27 | STOPPED_OUT |
| e19cfadb-1d70-45f9-b988-6ba7085e02c2 | 2026-07-27 | STOPPED_OUT |
| 7eecc72f-e493-483f-8340-98bb8a3248c4 | 2026-07-27 | STOPPED_OUT |
| ARTEMIS_NEE_20260727_144414_724504 | 2026-07-27 | STOPPED_OUT |
| HG_RBLX_20260727_143303_both | 2026-07-27 | STOPPED_OUT |

Three key formats still coexist within a single day: structured-numeric-tail
(`ARTEMIS_*_607745`), structured-token-tail (`HG_*_rsi`, `HG_*_both`), and bare UUID.

## ORPH-2a — stem-twin discriminator · 1 row

| n_orphans | with_stem_twin |
|---|---|
| **370** | **134** |

## ORPH-2b — UUID-key format split · 1 row

| uuid_keys | total |
|---|---|
| **61** | **370** |

## Orphan classes — disjoint, exhaustive

| class | n | note |
|---|---|---|
| stem twin exists in `signals` | 134 | key-variant drift; parent exists under a different final segment |
| UUID-keyed | 61 | parentless writer; cannot hold a stem twin (no `_` to strip) |
| neither | **175** | genuinely parentless, structured key (+1 since 08-03) |
| **total** | **370** | |

## Duplicates: ZERO, now measured directly

The 2026-08-03 run *derived* D = 0 from `D + O = 369` with `O = 369`. That derivation depended
on QS-02's 902 figure. It has now been tested at source rather than inferred:

```
signal_outcomes rows with a duplicate signal_id = 0
extra rows attributable to fan-out              = 0
```

`COUNT(*)` does not fan out on this join. QS-04-2 (G1v2) bucket counts are safe from
inflation. The live failure mode is the other one: **370 graded outcome rows anchor on
`signals` and are invisible to any LEFT JOIN taken from that side.**
