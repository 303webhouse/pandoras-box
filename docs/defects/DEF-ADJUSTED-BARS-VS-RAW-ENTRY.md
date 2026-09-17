# DEF-ADJUSTED-BARS-VS-RAW-ENTRY — P1

**Registered:** R-IV.425(a). **Contaminates every retrospective outcome.**
**Scope read:** CC-QUERY (how many graded rows, on every surface including
`triton_flow_shadow`, have a corporate action in the relevant window).
**Code-path facts below:** measured by CC-BUILD, 2026-09-16.

---

## THE STATEMENT

> **Stored and fetched bars are split/dividend-ADJUSTED. `entry_price` is RAW at fire.
> A return computed from one against the other is a return on two different price scales.**

Spine's known instance: **16 rows showing 70–150% fake returns.**

## WHY IT HAPPENS — two windows, one rule

An adjusted series rescales every price **before** a corporate action, as of the day it is
downloaded. So there are two ways a raw entry and an adjusted exit disagree:

| event falls… | raw entry P_T | exit price used | result for a 2:1 split, no real move |
|---|---|---|---|
| **between fire and exit** | pre-split, 100 | post-split, 50 (adjusted = raw here) | **−50%**, true 0% |
| **after exit, before the grade is computed** | pre-split, 100 | pre-split close, but re-scaled to 50 | **−50%**, true 0% |

**The second window means the contamination is not a property of the row — it depends on WHEN
the outcome was computed.** A regrade or a backtest run after a split silently changes rows that
were right when first graded. A reverse split gives the large *positive* fake returns.

**Both windows close under one rule:** take both ends from the **same series, downloaded at the
same time** — both adjusted or both raw. (A raw series still fails the first window for a split,
so "both raw" is only correct with the split factor applied; "both from the stored adjusted
series" is correct in both.)

## WHERE ADJUSTED BARS ENTER — measured

**yfinance's `download()` returns ADJUSTED prices when `auto_adjust` is not passed** — the
signature shows `None`, and the runtime says so itself: *"YF.download() has changed argument
auto_adjust default to True"*. Verified 2026-09-16 on 0.2.59: KO close for 2026-06-01, default call **77.6721**, `auto_adjust=False`
**78.6400**. `Ticker.history()` adjusts by default as well.

| call site | adjust setting | role |
|---|---|---|
| `jobs/outcome_resolver.py:116` | **default → adjusted** | grades signal outcomes |
| `jobs/score_signals.py:97` | **default → adjusted** | scores signals |
| `jobs/a3_fwd_return_resolver.py:90` | `auto_adjust=True` | forward returns |
| `integrations/uw_api.py:1674, 1700` (`get_bars_yfinance`) | **default → adjusted** | **the Triton grader's fallback bar source** |
| `analytics/price_collector.py:239, 241` | `auto_adjust=True` | price history |
| `stable_engine/bars_yf.py` (`_AUTO_ADJUST = True`) | adjusted | Stable Engine daily bars |

**About 40 further call sites** (scanners, bias filters, scheduler) use the default and are
therefore adjusted too; they compute indicators rather than outcomes, so they are listed in the
scope read rather than here.

**For R-IV.425(a)'s Triton question — the code-path half:** the Triton grader's yfinance
fallback fetches **adjusted** bars. Whether any *graded* Triton row actually had a corporate
action in either window is the data half, and it is CC-QUERY's to state.

## A SECOND, SEPARATE INSTANCE — the Stable Engine series mixes adjustment bases

`stable_engine/bars_yf.download_and_store` runs nightly with `days=15`: it re-downloads **only
the last 15 days**, adjusted **as of that night**, and upserts them. Rows older than 15 days keep
the adjustment that applied **when they were downloaded**.

**After any split or dividend, `stable_daily_bars` therefore holds two adjustment bases with a
seam 15 days back**, and `compute_metrics` recomputes the whole history (MA20/50/200, 20-day
returns, ATR extension, new highs) across that seam every night. For a dividend the step is
small; for a split it is the full split ratio, landing as a fake gap inside every
moving-average and return window that spans it.

**This is not raw-vs-adjusted — it is adjusted-vs-adjusted at different dates — and the rule
above does not fix it.** Its fix is to re-download a ticker's **full** history whenever its
adjustment basis changes (detectable: yesterday's stored close no longer matches yesterday's
freshly downloaded close), or to store raw bars plus factors and adjust on read.

## FIX SHAPE (R-IV.425(a))

1. **Outcomes are computed from the stored series at BOTH ends** — never a stored raw
   `entry_price` against an adjusted series — **or** the adjustment factor is stored at fire
   and applied.
2. **The backtest module takes this as a founding requirement: its SECOND acceptance test** is
   a fixture with a split between fire and exit and one after exit, and the module must report
   the true return in both.
3. Every bar fetch that feeds an outcome **states its adjustment explicitly** — no call relies
   on a library default that has already changed once.

## Status: OPEN — registered; scope read with CC-QUERY; fix lands with the backtest module.
