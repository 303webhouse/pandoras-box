# Earnings Gap Characterization -- 10-event study

**Brief date:** 2026-06-01  |  **Run date:** 2026-06-02  |  **Events:** 10 across 9 symbols (PLTR x2)

**Headline question:** how often does a big gap produce a fast secondary move (>=5%)  
that makes a cheap OTM option pay? Convexity columns are left-anchored.

**Data cutoff rule:** only confirmed closed sessions (bar date < run date).  
PENDING = session not yet closed. Cells are never estimated from partial data.

**Data cutoffs (last confirmed bar per ticker):**
  - NOW: 2026-06-01
  - PLTR: 2026-06-01
  - NXPI: 2026-06-01
  - F: 2026-06-01
  - TSN: 2026-06-01
  - NVDA: 2026-06-01
  - WMT: 2026-06-01
  - ZS: 2026-06-01
  - DELL: 2026-06-01

---

## Results

| C5 | UP(T5) | DN(T5) | DIR5 | C10 | UP(T10) | DN(T10) | DIR10 | LABEL | ROLE | GAP% | MAG | H/F | VOL | FILL | T+3 | T+5 | T+10 |
| ---- | -------- | -------- | ------------- | ---- | -------- | -------- | ------------- | --------- | ---------------------------- | ------- | ------- | ------- | ----- | --------- | -------- | -------- | -------- |
| Y | +4.2% | -12.9% | continuation | Y | +4.2% | -16.0% | continuation | NOW Q4 | beat-but-dropped fade | -8.6% | large | NEUTRAL | 5.0x | unfilled | -6.0% | -12.1% | -11.5% |
| Y | -1.3% | -18.7% | reversal | Y | -1.3% | -20.0% | reversal | PLTR Q4 | continuation-up | +11.7% | large | NEUTRAL | 3.3x | T+1 | -13.9% | -11.6% | -14.3% |
| Y | +5.1% | -3.3% | continuation | Y | +6.0% | -3.3% | continuation | NXPI Q1 | monster continuation-up | +22.1% | large | HOLD | 4.7x | unfilled | +0.5% | +4.9% | +3.2% |
| Y | +1.8% | -5.2% | continuation | Y | +23.7% | -5.2% | both | F Q1 | non-tech, full window | -5.6% | medium | FAIL | 2.2x | T+4 | -3.2% | +0.8% | +19.9% |
| Y | +1.1% | -5.2% | reversal | Y | +1.1% | -5.2% | reversal | TSN Q2 | non-tech up | +2.4% | small | HOLD | 2.9x | T0 | -1.2% | -2.4% | -3.0% |
| N | +3.7% | -3.5% | none | Y | +3.7% | -5.3% | continuation | PLTR Q1 | FAILED gap / negative case | -3.9% | medium | HOLD | 1.9x | unfilled | +1.4% | +0.1% | -0.5% |
| N | +0.7% | -4.9% | none | PENDING | PENDING | PENDING | PENDING | NVDA Q1 | MUTED control | -0.5% | small | HOLD | 1.4x | T0 | -3.1% | -3.8% | PENDING |
| Y | +0.5% | -5.5% | continuation | PENDING | PENDING | PENDING | PENDING | WMT Q1 | non-tech, partial window | -4.9% | medium | HOLD | 4.1x | PENDING | -2.3% | -4.6% | PENDING |
| PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | ZS Q3 | gap-down, short window | -25.7% | large | HOLD | 11.4x | PENDING | +23.2% | PENDING | PENDING |
| PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | PENDING | DELL Q1 | monster gap, minimal window | +31.8% | large | HOLD | 6.2x | PENDING | PENDING | PENDING | PENDING |

---

## Column key

| Col | Meaning |
|-----|---------|
| C5/C10 | CONVEX flag: Y if max excursion >=5% in either direction over T+1..T+5 / T+1..T+10 |
| UP/DN | Max up / max down excursion from T0 close over that window (DN shown negative) |
| DIR5/DIR10 | Whether the convex trigger was continuation (same dir as gap) or reversal |
| GAP% | (T0 open - T-1 close) / T-1 close. Sign = direction. |
| MAG | small <3%, medium 3-7%, large >7% |
| H/F | HOLD if T0 closed in top third (gap-up) or bottom third (gap-down); FAIL opposite; NEUTRAL middle |
| VOL | T0 volume / 30-session average before T0 |
| FILL | First session T0..T+10 where bar range crossed back through T-1 close |
| T+3/T+5/T+10 | % move from T0 close to that session's close. Sign is absolute (+ = up). |

*Re-run ~2026-06-15 to backfill PENDING cells for late-May names.*
