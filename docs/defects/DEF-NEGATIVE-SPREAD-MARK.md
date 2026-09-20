# DEF-NEGATIVE-SPREAD-MARK — debit spreads carried marks below zero, and one stood for three weeks

**Registered:** R-IV.462(d); accepted R-IV.463(d) at **14 positions within audit reach**. The
audit covers 2026-05-26 onward; **before that is unknown**. **Found:** CC-BUILD, 2026-09-19,
reading the first cycle of the legs mark path. **Status:** FIXED FORWARD (R-IV.462, R-IV.463(a)(c)).
The historical figures stay in the audit and are on record here, so the impossible numbers are
not merely gone.

> A debit spread cannot be worth less than nothing. A mark below zero is not a price: it is two
> quotes taken at different moments, subtracted.

**ROOT CAUSE: legs priced at different moments.** A live mid on one leg and a weeks-old last trade
on another subtract to a price nobody could trade at.

**AND THE GUARD THAT WOULD HAVE CAUGHT IT WAS WIRED INTO ONE OF TWO WRITE PATHS. A guard wired
into one of two write paths is a guard on neither.** T1 (R-IV.394) refuses a mark at or below
zero, but only the PATCH recompute called it. The mark job, which writes nearly every mark, never
did.

**A STALE QUOTE THAT IS STILL POSSIBLE PASSES THE PAYOFF BOUND SILENTLY.** The bound (R-IV.462)
catches only impossible results. So since R-IV.463(a), a MARK takes nothing but a two-sided quote
or a trade from the current session. Chains and greeks keep the wider fallback: a chain is a
lookup, and a mark is a claim about what the principal holds right now.

---

## THE INSTANCE — SLV 316

| field | value |
|---|---|
| structure | `call_debit_spread`: long 120C / short 130C, expiry 2026-09-30, quantity 5, entry 0.0562 |
| stored leg prices | long 120C **0.02**, short 130C **0.105**: the higher-strike call priced above the lower |
| mark | **−0.085** |
| unrealized shown | **−70.60** = (−0.085 − 0.0562) × 5 × 100 |
| first negative write | 2026-08-28 20:47:06 UTC |
| last refresh (`price_updated_at`) | 2026-08-31 13:17:07 UTC; the figure stood unrefreshed from then on |
| cleared | 2026-09-19 05:28:15 UTC, first legs cycle: a negative prior is never kept (4d3e7e2) |
| evidence | `position_sync_audit.before_state` of the 05:28 write holds the −0.085 and the −70.60 |

## THE CLASS: 14 positions

Every row the audit trail recorded with `current_price < 0`:

| id | ticker | structure | status now | negative writes | first | last | most negative | worst unrealized |
|---|---|---|---|---|---|---|---|---|
| 37 | STUB | call_debit_spread | CLOSED | 1 | 09-18 04:31 | 09-18 04:31 | −0.010 | −88.00 |
| 304 | PLTR | put_debit_spread | CLOSED | 1 | 08-27 16:47 | 08-27 16:47 | −0.015 | −17.80 |
| 313 | IBIT | put_debit_spread | CLOSED | 1 | 09-18 04:31 | 09-18 04:31 | −0.005 | −42.50 |
| 316 | SLV | call_debit_spread | OPEN | 4 | 08-28 20:47 | 09-18 04:31 | −0.085 | −70.60 |
| 355 | QQQ | put_debit_spread | OPEN | 10 | 09-01 19:02 | 09-10 16:17 | −0.010 | −232.80 |
| 356 | QQQ | put_debit_spread | OPEN | 14 | 08-27 13:02 | 09-18 19:32 | −0.010 | −50.80 |
| 363 | ORCL | put_debit_spread | OPEN | 2 | 08-27 13:02 | 08-27 13:17 | −0.050 | −91.10 |
| 367 | WEAT | call_debit_spread | OPEN | 10 | 09-02 20:47 | 09-14 14:47 | −0.175 | −67.50 |
| 376 | UVXY | call_debit_spread | OPEN | 69 | 08-27 13:02 | 09-15 15:02 | −0.245 | −154.36 |
| 380 | SPCX | put_debit_spread | OPEN | 77 | 08-28 14:17 | 09-02 20:32 | −0.065 | −43.80 |
| 381 | TGT | put_debit_spread | EXPIRED | 17 | 08-27 17:47 | 08-28 13:17 | **−0.560** | −152.18 |
| 407 | QQQ | put_debit_spread | EXPIRED | 1 | 09-04 15:32 | 09-04 15:32 | −0.015 | −16.50 |
| 423 | UVXY | call_debit_spread | OPEN | 4 | 09-15 13:02 | 09-15 15:02 | −0.110 | −12.00 |
| 427 | QQQ | put_debit_spread | OPEN | 3 | 09-18 20:17 | 09-18 20:47 | −0.005 | −34.00 |

All times UTC, 2026. STUB 37 and IBIT 313 are closed and still store their negative mark. A closed
row's result is its realized figure, and those rows were left as they are.

**What the instrument could see (#18, addendum 3; corrected by R-IV.464(d)).** The audit records
UPDATE and DELETE, only when a row changed, and the CONTINUOUS trail starts **2026-08-26 21:02:24
UTC** -- the twenty rows before it are two CSV-sync runs' own records (2026-05-26, 2026-07-19),
not a record of every write. A negative mark written before that instant, or held in a row that
was never rewritten, cannot appear here. **Fourteen is the count from 2026-08-26 21:02 UTC
onward; before it, unknown.**

## THE MECHANISM

1. **The guard existed, and the mark job never called it.** T1 (R-IV.394) refuses a mark ≤ 0 and
   writes nothing on a refusal. It was wired only into the PATCH recompute. The mark job, the
   writer behind nearly every mark, stored values T1 would have refused. The rule was in the
   source and the system never read it (Law 2).
2. **The legs were priced at different moments.** The two-strike path computes `long_mid −
   short_mid`. When a leg has no two-sided quote, `_get_contract_mid` falls back to the last trade,
   then the day's close, then VWAP, **of any age**. SLV's stored legs show the result: the 130C at
   0.105 above the 120C at 0.02. *Inferred from the stored leg prices; the vendor's per-leg trade
   times were not read.*
3. **The first legs path would have hidden it.** 1ab7fe4 (2026-09-18) stored `abs()` of a leg
   set's net, which turns −0.085 into +0.085, an invented gain. QQQ 356 and 427 carried negative
   two-strike marks on 09-18 and read +0.01 / +0.005 after the first legs cycle. The legs path
   did not store its leg quotes, so those nets cannot be recovered. For QQQ 356, though, the
   chain read at 06:14 UTC shows the 360P at 0.02 under the 350P at 0.03: a net of −0.01, which
   the bound refused at 06:13. The prior it kept, 0.01, is exactly abs(−0.01). **A legs prior
   now counts as good only if the bound checked it.** Marks from before the bound do not carry
   the marker, so they are cleared on their next failed cycle, not kept.

## THE FIX (R-IV.462)

- **T1 reaches the mark job, on both paths.** On the two-strike path a rejected mark writes
  nothing to the price or the P&L: the prior stands, stamped `REJECTED` with the reason. On the
  legs path a rejection is a failed cycle under the legs guard.
- **A leg set's value is bounded by its payoff.** Any set of legs, one structure of it, is worth
  something between the lowest and highest its expiration payoff can reach. A debit vertical is
  worth between 0 and its width, a long butterfly between 0 and its wing, and a long call has no
  ceiling. A net outside that range reads UNAVAILABLE for the cycle, with the range in the reason.
  It reads the legs only, with no structure allowlist.
- **On the two-strike path, a vertical priced above its width is refused.** T1 covers the floor.
- **A negative prior is never kept** (4d3e7e2).

## CLOSED BY R-IV.463

- **(a) A mark takes a two-sided quote or a trade from the current session, nothing older**
  (`utils/options_math.compute_mark`, and `for_mark=True` on the three pricers, set by the mark
  job alone). The vendor reports no trade time. A contract's session volume above zero is the
  evidence that its last price is from that session (on a weekend, Friday's session). A leg
  without either reads UNAVAILABLE or STALE, with the reason naming the leg, its bid, ask and
  volume.
- **(c) `abs()` is retired.** A mark is the SIGNED net in the side the position was entered on:
  the value held for a debit, the cost to close for a credit. A set that crosses zero now reads
  negative instead of folding back positive. The side follows from the legs:
  1. their payoff, when it cannot change sign;
  2. their fills;
  3. the side recorded at entry (`entry_side`).
  With none of these, the mark is UNAVAILABLE rather than guessed. T1's floor applies where the
  value cannot go negative. Where it can, the payoff range is the floor.

## STILL NOT FIXED — named so they are not mistaken for fixed

- **Chains and greeks keep the wide fallback, by ruling.** Any reader that takes a chain's `mid`
  as a mark reintroduces the root.
- **A calendar or diagonal is bounded per expiry, not jointly.** The near and far legs are each
  checked, but nothing bounds their combination. A stale-but-possible quote on one of them
  passes.
- **Two closed rows still store a negative mark**, STUB 37 (−0.010) and IBIT 313 (−0.005). A
  closed row's result is its realized figure; these marks are left as the record of the defect.
