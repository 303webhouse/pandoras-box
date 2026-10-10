# LAB-CAL part (a): fixed calendar tags, design only (R-IV.823(j), Task 7)

**Status:** DESIGN. No code, no data, no result. Dated 2026-10-10.
**Scope:** part (a), the fixed calendar only. Part (b) (leveraged-ETF rebalance estimates,
closing imbalances, ETF creations/redemptions) stays PARKED (R-IV.823(k)).
**Triton:** none of these tags is applied to Triton rows before read 7, Fri 2026-11-06
(R-IV.677(c)). After read 7, applying them is a new decision, not a default.
**Use:** reporting splits for the census, replays and registered tests. **A tag is never an entry
gate** unless a later registration makes it one, and then it counts on that strategy's tries
counter.

## 1 · What already exists, and what it gets wrong
| existing | file:line | finding |
|---|---|---|
| `is_opex_week` on every signal row | `backend/analytics/calendar_context.py:54-65` (`_third_friday`, `check_opex_week`) | **third Friday with no holiday shift.** When that Friday is an exchange holiday (e.g. Good Friday), monthly options expire the Thursday before, and the week tag is off. LAB-CAL replaces the date rule and keeps the field name. |
| `market_event` on every signal row | `calendar_context.py:192-233`, reading `backend/data/market_events.json` | **the file holds 7 events, the last on 2026-03-18** (committed 2026-02-17). Every signal since March carries `market_event = NULL`, and there is no FOMC history for any replay. |
| trading days and holidays | `backend/stable_engine/market_calendar.py` (`is_trading_day`, `previous_trading_day`, `CALENDAR_FIRST` 2025-01-01, `CALENDAR_HORIZON` 2027-12-31) | the one calendar. LAB-CAL builds on it. Its range must reach back to **2007** for the replays (an extension, §4). |

## 2 · The tags (all keyed on an exchange trading day d; "trading day" = `market_calendar`)
| tag | definition | values |
|---|---|---|
| `tom_pos` | **turn of month.** Position relative to the month boundary: the last trading day of a month is −1; the first three trading days of the next month are +1, +2, +3 | −1, +1, +2, +3, or null |
| `tom` | `tom_pos` is not null | bool |
| `month_end` | d is the last trading day of its calendar month | bool |
| `quarter_end` | `month_end` and the month is Mar / Jun / Sep / Dec | bool |
| `tdays_to_month_end` | trading days from d to its month's last trading day (0 on that day) | int |
| `opex_day` | **monthly equity options expiration:** the third Friday of the month; if that Friday is not a trading day, the last trading day before it | bool |
| `opex_week` | d falls Monday to `opex_day` of the expiration week (the existing field's meaning, on the corrected date) | bool |
| `quad_witching` | `opex_day` in Mar / Jun / Sep / Dec (index futures, index options, single-stock options and futures expire together) | bool |
| `fomc_day` | d is a **scheduled** FOMC statement day (the second day of a two-day meeting) | bool |
| `fomc_pos` | position relative to the nearest scheduled statement day: −1, 0, +1 | −1, 0, +1, or null |
| `fomc_unscheduled` | d is an unscheduled (emergency) FOMC action, kept apart from scheduled | bool |
| `sp_rebalance` | the S&P 500 quarterly rebalance effective date: changes take effect after the close of the third Friday of Mar / Jun / Sep / Dec (holiday-shifted as `opex_day`). Ad-hoc index changes are not fixed-calendar and are excluded | bool |
| `russell_recon` | the Russell US reconstitution effective date(s) **as published by FTSE Russell for that year**, stored as dated rows with their source (see §3). It is not computed by rule, because the schedule has changed over time | bool |
| `buyback_blackout_est` | **estimated** aggregate buyback blackout, fixed-calendar proxy: from **14 calendar days before each quarter-end** to **30 calendar days after it**. No company data is used, so this is an estimate, labelled as one everywhere it appears. Part (b) could refine it with earnings dates; part (b) is parked | bool |
| `buyback_blackout_pos` | trading-day index inside that window (0 = first day), for dose-response splits | int or null |

**Why these definitions.**
- TOM −1..+3 is the window the turn-of-month literature uses.
- The third-Friday-with-holiday-shift rule is the listed equity options' expiration rule.
- FOMC uses statement days because that is when the information arrives.
- The buyback window is the common sell-side proxy (blackouts open about two weeks before
  quarter-end and close about 48 hours after each company's report). Thirty days after
  quarter-end covers the bulk of reporting season. Its looseness is why it is an estimate.

## 3 · Source tables (static, versioned, each row with its source)
| table | rows | source and verification |
|---|---|---|
| `fomc_meetings` | scheduled statement dates 2007 → 2027, plus unscheduled actions flagged | the Federal Reserve's published FOMC calendars and historical materials. Each year is verified against the Fed's page before it is used; the verification date is stored on the row |
| `russell_recon` | effective dates by year | FTSE Russell's published reconstitution schedule for that year. **Not asserted here from memory**: the schedule has changed, and each year is entered from the published document with its citation |
| `holidays` | — | none new: `market_calendar.MARKET_HOLIDAYS` is the one list. LAB-CAL extends its range (§4), it does not fork it |

Static tables live in the repo as data files with a header row naming the source and the
verification date, the way `market_events.json` was meant to work. They are not fetched at run
time.

## 4 · Implementation sketch (for a later build, not now)
- **Module:** `backend/analytics/lab_calendar.py`, pure. `tags_for(d) -> dict` computes the table
  in §2 from `market_calendar` plus the §3 files. It never raises: an out-of-range date returns
  every tag as null, with a `reason`.
- **`market_calendar` range:** extend `CALENDAR_FIRST` back to 2007-01-01 for the replays.
  `_check` currently refuses dates outside 2025–2027. The extension is a holiday-list addition,
  verified year by year against NYSE's published holidays and early closes.
- **Fix in place:** `calendar_context.check_opex_week` delegates to `lab_calendar` (holiday
  shift). `market_event` reads `fomc_meetings` and stops depending on the stale JSON for FOMC.
  NFP and CPI stay where they are, out of LAB-CAL's scope.
- **Reporting:** the census and replay harnesses gain a `--split calendar` that reports each
  figure by tag, with n and n distinct dates per cell. That is a split, never a filter.
- **Tests:**
  - known days: a quad-witching Friday; a holiday-shifted expiration Thursday; a month-end that
    falls on a Friday holiday;
  - an FOMC statement day from the verified table;
  - a range error that returns nulls, not an exception;
  - the buyback window's first and last days around a quarter-end.

## 5 · What part (a) deliberately does not do
- No vendor data, no flows, no estimates beyond the buyback proxy (that is part (b), parked).
- No tag applied to Triton rows before read 7.
- No tag used as a gate in any live strategy.

## Change log
- 2026-10-10: v0 design (R-IV.823(j)).
