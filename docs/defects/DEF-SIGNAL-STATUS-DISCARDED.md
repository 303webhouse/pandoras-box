# DEF-SIGNAL-STATUS-DISCARDED · P2

**Found:** 2026-09-02, during the STRIKE-SPEC-01 build (Task 2).
**Found by:** CC-BUILD, running the brief's own D4 regression premise as a check
rather than as an assumption.
**Status:** TICKETED, NOT FIXED — brief Gates: *"Defects encountered are ticketed,
not fixed."*

---

## The defect

`log_signal()` accepted a `signal_data` dict, and **silently discarded its
`status` key**. The column's `DEFAULT 'ACTIVE'` then stamped every inserted row
regardless of what the caller had decided.

Six sites set `signal_data["status"]` before persistence:

| site | value | reaches the INSERT? |
|---|---|---|
| `webhooks/tradingview.py:538` | `IGNORE` | **YES** |
| `signals/pipeline.py:1217` | `ACTIVE` (default) | YES — benign, it is the default |
| `signals/pipeline.py:1290` | `REJECTED` | no — `return signal_data` at :1296 |
| `signals/pipeline.py:1325` | `REJECTED` | no — `return signal_data` at :1329 |
| `signals/pipeline.py:943` | `DISMISSED` | no — caller runs at :1536, **after** the insert |
| `signals/pipeline.py:170` | `COMMITTEE_REVIEW` | no — caller runs at :1567, **after** the insert |

Only one live path is affected, and it is affected on every occurrence.

## The live path

```
webhooks/tradingview.py:538   suppressed Exhaustion BULL -> signal_data["status"] = "IGNORE"
  -> :553  _process_with_market_structure(signal_data, source="tradingview")
  -> signals/pipeline.py  process_signal_unified(...)
  -> :1217 signal_data["status"] = signal_data.get("status", "ACTIVE")   # preserves IGNORE
  -> :1403 await log_signal(signal_data)                                  # IGNORE discarded here
```

The accompanying `signal_data["note"]` is discarded by the same mechanism —
`log_signal` writes `notes`, never `note`.

## Why it is P2 and not P3

`status = 'ACTIVE'` is a **read gate on live surfaces**:

- `api/board_state.py:134`
- `api/trade_ideas.py:53`, `:294`, `:489`

So suppressed Exhaustion BULL signals — rows the emitting code explicitly
decided to suppress — have been **visible on the trade-ideas and board-state
surfaces the entire time**. The suppression decision is computed, written to the
dict, carried through the whole pipeline, and thrown away one line before it
would have taken effect.

This is the **compute-then-discard family**, sixth instance: `active_weight_sum`
· the `UWUnavailable` sentinel · per-row `is_stale` in `total_balance` ·
`darkpool_enrichment`'s return dict · `get_market_tide()` Redis-only · and now
`signal_data["status"]`.

## What SPEC-01 did about it

**Nothing to the defect.** SPEC-01 needed `log_signal` to persist `status='SHADOW'`,
and the brief specified the general form:

```python
signal_data.get("status") or "ACTIVE",
```

That form is **not additive**. It would have activated the dormant `IGNORE`
write on first deploy and removed those rows from both live surfaces — a
live-surface change inside a build whose first binding condition is
shadow-only invisibility. The brief's D4 regression check could not have caught
it either: D4 looks for stray `SHADOW` rows, and these would be `IGNORE`.

The build therefore ships the **scoped** form, which preserves current behavior
byte-for-byte for every existing caller:

```python
"SHADOW" if signal_data.get("status") == "SHADOW" else "ACTIVE",
```

**This is a deviation from the brief's literal text and is reported as one.**
It was chosen because it is the option that changes nothing outside SPEC-01's
scope; the brief's own form is the one that changes live behavior.

## Fix, when commissioned

Widening the scope is a one-line change *plus* a decision that is not
CC-BUILD's to make: **should suppressed Exhaustion BULL rows disappear from
trade-ideas and board-state?** The emitting code's intent says yes. Nothing has
depended on that intent for as long as the defect has existed, so the surfaces
have been showing them throughout, and someone may now be reading those rows as
signal.

That is a 3DTE / spine call, not a build call. Quantify first: count the
affected rows before changing what a live surface shows.

## Not verified

The historical incidence is **not measured**. `note` is discarded alongside
`status`, so no in-DB marker distinguishes a suppressed Exhaustion BULL row from
an unsuppressed one. Counting them requires either a code-side marker added
going forward or a join against the TradingView webhook logs. **No count is
asserted here.**
