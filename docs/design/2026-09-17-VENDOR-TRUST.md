# VENDOR TRUST, SCOPED BY USE

**R-IV.436(a), rule of record.** **Author:** CC-BUILD, 2026-09-17.
**Companion to:** conventions #20 (every stored price names its vendor and its basis) and #21
(a substituted vendor is announced).

---

## THE RULE, IN TWO HALVES

**TRUSTED — bar geometry within a single fetch.** Highs, lows, closes and their order inside
one series: detection, levels, breach tests, the shape of a bar. Every scanner runs on this and
is UNAFFECTED by what follows. A single fetch is internally consistent whatever basis it is on,
because every price in it was adjusted the same way at the same moment.

**NOT TRUSTED — returns across a corporate action.** A return computed from a price recorded at
one time against a series fetched at another is a return on two scales, and the vendor decides
the scale without telling anyone. **The graders are affected; the scanners are not.**

## THE MEASURED FAILURES BEHIND THE SECOND HALF

| what was measured | where |
|---|---|
| `auto_adjust=False` still returns SPLIT-ADJUSTED closes — the argument's name says otherwise | CC-QUERY, R-IV.425(a) scope read (CRWD 04-27 close 113.65 against a raw ~455) |
| dividends silently dropped on that same path, so a "price return" is only sometimes one | same |
| the calendar lists a factor the closes do not carry, and elsewhere the fresh series applies it in the WRONG DIRECTION, inflating pre-ex prices | HON 0.9535, 2026-06-29 |
| a partial refresh leaves two bases inside ONE stored series, with the seam two weeks before the ex-date | APH 2-for-1, ex 2026-09-03 |
| a raw entry against an adjusted series produced stored returns of -94% and +95% | Triton rows 38201 / 80352, KORU 20-for-1 |

## WHAT FOLLOWS FROM IT

- **Scanners:** unchanged. Geometry inside one fetch is what they use.
- **Graders:** a row whose window spans a split-calendar event is **HELD, never graded** —
  the backtest module at R-IV.432(e), the Triton grader at R-IV.436(b), on either vendor path.
- **Every graded row records its vendor and basis** (conventions #20), so a figure can be
  re-read later against the basis it was computed on.
- **A substitution is announced** (conventions #21): which vendor actually served.

## R-IV.436(d) — THE TIEBREAK IS INDEPENDENT, OR IT IS NOT A TIEBREAK

The split calendar and the bars come from the **same vendor**. A vendor that adjusts wrongly
also "confirms" its own adjustment, so its calendar cannot settle a disagreement about its own
bars — that is the Law 2 instance this rule exists for.

**When a held row has to be resolved, the tiebreak is a price from somewhere else:**

1. **UW `spot_at_fire`** (Triton rows) or the **raw entry price** recorded by the producer at
   fire — neither passes through the bar vendor;
2. **the second vendor's closes** for the same sessions (the backtest module's check);
3. **never** the bar vendor's own calendar as the deciding voice.

If no independent price exists for a row, it **stays held**. A held row is a known gap; a
wrongly graded row is a number that will be quoted.

## SCOPE OF THE VENDOR-AGREEMENT CERTIFICATE (R-IV.436(c))

The 102-of-102 certificate proves **VENDOR AGREEMENT ON ORDINARY DAYS** — UW and yfinance
returning the same closes to the cent on liquid tickers. **It does not prove ADJUSTMENT
CORRECTNESS ACROSS A CORPORATE ACTION**, and it could not have: its sampling frame required
presence in `stable_daily_bars`, and the rows that could have failed were exactly the rows that
membership excluded (the Law 1 instance, filed in Addendum 3 at R-IV.428(c)).

The statement is repeated on the filed certificate's own face.
