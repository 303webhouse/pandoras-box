# DEF-STABLE-REGIME-FROM-N2 · P1

**Registered** 2026-09-10 by R-IV.338(d). **Measured live the same day.** **Status:** OPEN.
**P1: decision surface.**
**Read of record:** `docs/edge/results/2026-09-10-d3-aegis-and-regime-n1.md`

**The name says n=2. The live read says n=1.** Kept as registered so the citation resolves;
the measurement is below.

---

## Measured, 2026-09-10

```
regime_label  "RISK-OFF"
breadth       total 1
              pct_above_50dma 0.0   pct_above_200dma 0.0   pct_above_20dma 0.0
              up_3 0   down_3 0   new_high_20d 0   new_low_20d 0
thresholds    risk_off <= 40   risk_on >= 60   big_move 3.0%
```

**0 of 1 is 0%, 0% is below 40, therefore RISK-OFF.** **The board's regime label is one
ticker's position relative to its 50-day moving average.**

## The filter is correct. The input is starved.

`get_regime_read()` (`backend/stable_engine/scoring.py:198-228`) computes breadth from
`stable_metrics` at `MAX(date)`, joined to `stable_universe`, excluding `Benchmark`,
`Scan Only` and `Sector ETF`.

**Those exclusions are deliberate and right** — benchmarks and sector ETFs would double-count
the market against itself. **`total = 1` means the metrics table holds ONE qualifying row at
its most recent date**, not that the filter is over-tight.

**Named as related, not as proven cause:** `DEF-STABLE-NIGHTLY-SUCCEEDS-WITHOUT-ADVANCING`
was filed one day earlier — the nightly reports success while `stable_daily_bars` ends
2026-09-04. **A metrics table with one qualifying row at `MAX(date)` is the shape of a
partially-written day.** Whether it is the same cause is unread.

## Why P1

**A regime label is a conditioning input.** It is read by the committee to decide whether
the tape supports a direction, and **nothing in the payload says the breadth behind it is a
single instrument.** The label is served with the same confidence at n=1 as at n=400.

**And the threshold arithmetic degenerates.** With `total = 1`, `pct_above_50dma` can only
take the values 0 or 100 — **so the label can only ever be RISK-OFF or RISK-ON, never the
middle band.** A three-state classifier with a two-state input is not measuring the market;
it is measuring one ticker with extra steps.

## It reaches the theme scores too, on at least one anchor

`compute_provisional_theme_scores()` (`backend/stable_engine/live.py:69-105`) filters the
base once and uses it twice:

```
:75    base = base[base["ticker"].isin(live.keys())]
:88    scan = base[...]                    -> breadth_counts
:105   for theme, group in base.groupby("theme")  -> theme scores
```

**Same DataFrame, seventeen lines apart.** On the provisional anchor, whatever starves
breadth starves every theme score identically — **and the theme panel renders confident
numbers either way.**

**The close anchor is NOT verified here.** The served `dominant` / `emerging` lists read
from stored `stable_theme_scores`, and which anchor the endpoint serves was not established.
**Stated as a gap.** (Conventions #14: this lane has twice this week inferred a runtime path
from a static read and been wrong.)

## Fix shape — not chosen here

**A breadth count below a stated floor is not a regime.** The honest render is
`INSUFFICIENT n=<count>` — the same form the STRIKE watermarks already use, and for the same
reason: **a classifier below its minimum sample must say so rather than classify.**

**The floor is a decision, not an implementation detail**, and it needs the same §1.1
treatment as any other predicate: declare the expected satisfaction rate, and demonstrate
the INSUFFICIENT state is reachable.
