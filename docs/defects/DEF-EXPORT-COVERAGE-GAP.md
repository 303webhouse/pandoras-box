# DEF-EXPORT-COVERAGE-GAP

**Severity:** P2 · **Filed:** 2026-09-07 (R-IV.313(e)) · **Status:** OPEN
**Author:** CC-POSITIONS — sole author under convention #9.
**Surface:** `data/imports/` — the broker export corpus, both accounts
**Class:** acceptance-blocking. Not a data error; an *absence of the artifact* that data errors
are adjudicated against.

## THE DEFECT

**No export on disk carries a single September 2026 activity line, on either account.**
Measured 2026-09-07 by parsing each file's own activity-date column:

| export | activity-date range | rows | Sept 2026 rows |
|---|---|---|---|
| `rh-8.31.2026.csv` | 2025-12-09 → **2026-08-31** | 1,869 | **0** |
| `3b84f64e-…csv` | 2026-08-17 → 2026-08-25 | 61 | **0** |
| `FID_History_8.27.2026.csv` | 2026-08-17 → 2026-08-28 | 56 | **0** |
| `90-day Accounts_History.csv` | 2026-05-27 → 2026-08-25 | — | **0** |
| `History_for_Account_…csv` | 2026-06-25 → 2026-08-25 | — | **0** |

**Newest coverage anywhere: 2026-08-31.** Every position opened in September is unverifiable.

## WHY IT BINDS

`TA-009` (standing rule, `docs/trading-theses.md`): *no row is acceptance-tested, and no figure
marked `BROKER_VERIFIED`, without an export covering its entry date.* With no September
coverage, every September row is capped at **`SCREEN_VERIFIED`** — corrected from the broker's
positions screen, which shows *current state* and not *the events that produced it*.

A screen can say "you hold 20 at 49.1225." It cannot say whether the other 10 were sold, at
what price, or whether they were ever filled. That distinction is a realized-P&L question, and
no screenshot answers it.

### Confirmed instance — id 409 SOXS

Corrected 2026-09-06 to qty 20 @ 49.1225, basis 982.45, `max_loss` 982.45 explicit;
provenance **`SCREEN_VERIFIED`**, flips to `BROKER_VERIFIED` on a September export.
**The 10-lot's fate is OPEN and deliberately not asserted:** sold (a closed row and its
realized are owed) or never filled (the 09-03 entry was phantom) cannot be distinguished from
what is on disk.

## WHAT MAKES THIS DIFFERENT FROM DEF-RH-COVERAGE-GAP

`DEF-RH-COVERAGE-GAP` is about **events the DB failed to record** when a source existed.
This is about **no source existing to record from**. The remedies do not overlap:

- A lots table fixes prose-only and one-ledger-of-two failures.
- **A lots table does not fix this.** A lots table with no artifact to populate it is an empty
  lots table. Crediting the lots table for this class over-credits the remedy.

## REMEDY

**A standing export cadence** — both accounts, on a fixed interval — until the ledger build's
import job exists. The interval sets the maximum age of an unverifiable position; at present
that age is unbounded and grows daily.

Interim rule already in force: **TA-009**. Every screen-sourced correction must say the export
was silent, so an unverified figure is never mistaken for a verified one.

## STATUS

Registration only. **No fix authorized, no rows touched by this filing.** The id 409 correction
was made under R-IV.312(c) and carries its own provenance.
