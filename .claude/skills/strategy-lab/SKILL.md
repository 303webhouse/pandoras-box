---
name: strategy-lab
description: >
  CC-LAB's protocol for every signal strategy in Pandora's Box — defining it, replaying it
  on history beside a control, registering a forward test, shadowing it, and getting it to a
  surface. Use whenever work touches a strategy's definition, its code, a historical test or
  replay, a parameter variant, a strategy card under docs/strategies/, a signal census, or a
  registration. Also use before quoting any strategy return figure. Don't undertrigger: if
  the question is "does this signal work" or "should this signal change", this skill
  governs the answer.
---

# Strategy Lab protocol

Charter: R-IV.823, amended by R-IV.826. This file is the working form of both. Where it
disagrees with a later SPINE ruling, the ruling wins and this file gets a change-log entry.

**The one idea behind every rule below:** a strategy is judged on what it did *beyond the
market's own move*, on prices a person could actually have traded, against a control, by
someone who did not build it. Triton's apparent edge turned out to be the market's move.

---

## 1 · Lifecycle

```
DEFINE → REPLAY → REGISTER → SHADOW → VERDICT → SURFACE
```

| step | what happens | who | exit condition |
|---|---|---|---|
| **DEFINE** | the card is written (§7): rules, side, **grid cell it fills**, and **the incumbent it would replace** (or "none: fills an empty cell"). Anti-bloat class stated: REPLACES / ELEVATES / ADDS (PROJECT_RULES.md, Strategy Anti-Bloat Framework). | LAB | card committed on a `claude/lab-*` branch |
| **REPLAY** | a historical test **beside a control** (§4), both stages where the expression is options (§5). | LAB | result staged to the ferry (§9) |
| **REGISTER** | the rules and pass bar written and **hashed before the forward data exists** (§2). | LAB writes; QUERY receives the hash | hash relayed to SPINE and QUERY before the first forward session |
| **SHADOW** | the strategy emits and is graded, but is kept off actionable surfaces: its `signal_type` is in `SUPPRESS_ALWAYS` (`backend/config/l0_routing.py`). Grading continues under suppression by design. | LAB ships the code; BUILD merges | the registered stop date, or minimum n *and* minimum distinct dates reached |
| **VERDICT** | the registered text is executed verbatim on the forward data. | **QUERY, never LAB** | QUERY's artifact, which states the lifetime tries counter |
| **SURFACE** | removed from `SUPPRESS_ALWAYS`. Requires all of: a passing verdict, **both stages passed**, a TA note citing the verdict, **the principal's yes**, and a bucket inside the card's ceiling (§6). | TA + principal; BUILD deploys | — |

Retirement is not LAB's call: it stays with SPINE and QUERY (09-23 item S2). LAB may
*recommend* a kill by citing the card's kill rule.

## 2 · REGISTER — what the hash covers

A registration is one file, `docs/strategies/registrations/<name>-v<N>.md`, built on
`docs/edge/preregistrations/TEMPLATE.md`. It must state, and the hash therefore covers:

1. the **definition text**, verbatim;
2. the **code commit** (full SHA) that emits it;
3. the **universe rule** (point-in-time, or the survivorship caveat plus the ETF-only check, §4.6);
4. the **entry-price rule** (§3.1);
5. the **horizons** (§3.2);
6. the **primary metric** (the market-adjusted return, §3.3, unless stated otherwise with a reason);
7. the **controls** (§4);
8. the **decision rule**: pass / hold / fail, as a table, with the threshold for each;
9. **minimum n** *and* **minimum distinct dates**, with the expected satisfaction rate of each
   declared (verification-laws §1.1: a predicate that cannot be reached is a null trigger);
10. the **stop date**.

**How to hash.** `core.autocrlf` is true on this machine, so the working-tree file and the
committed file differ byte for byte. Hash the committed blob only:

```bash
git show <commit>:docs/strategies/registrations/<name>-v<N>.md | sha256sum
```

Then re-verify from a separate PowerShell process. Relay the SHA, the commit and the hash to
SPINE and QUERY. The branch push timestamp is the proof that it came before the data. A
registration is never edited after it is hashed. A change is a new version (§3.5) with a new file.

## 3 · Measurement rules

### 3.1 Entry price

**The first price a person could trade once the signal is known.** For a scan that runs after
the close, that is **the next session's open**. For an intraday trigger, it is the open of the
first bar *after* the bar that completed the signal. Never the signal bar's close and never a
coded entry level.

### 3.2 Horizons

Grade on **fixed horizons**, counted in sessions with the entry session as session 1; exit at
that session's close. **Never grade on touching a coded target or stop.** A coded target can
be reported as a secondary column, labelled as such.

### 3.3 Market-adjusted return: the headline of every result

Every return figure is reported **adjusted first, raw beside it**:

```
r_adj = r − β_adj · r_SPY        (same window: entry price → horizon close, both legs)
β_adj = 0.67 · β + 0.33
β     = OLS slope of the ticker's daily returns on SPY's daily returns over the
        60 sessions ending the session BEFORE the signal
```

- **At least 50 valid sessions** in that 60, otherwise β = 1 and the row carries a
  `beta_fallback` flag. The count of flagged rows is reported.
- **BEAR rows: flip the sign** of both r and r_adj, so a positive number always means the
  strategy made money.
- **Basis, stated on every result.** r and r_SPY use **raw (unadjusted) prices**, which is what was
  traded. β's daily returns use **adjusted closes**, because a split day inside the
  regression window would otherwise dominate the slope. A row whose *holding* window contains
  a split is excluded from that horizon and counted.
- **β is an adjustment, never an entry filter.** No strategy may select on β.
- Why: passive and mechanical flows can't be removed from prices; judging a strategy on what
  it did beyond the market's own move is how they are neutralised.
- **Triton exception:** Triton's registered C3 and C4 are unchanged. Adjusted figures may sit
  *beside* them and never replace them.

### 3.4 n beside every figure

Every figure is printed with **n fires and n distinct dates**. Signals cluster on days. A
hundred fires on four dates are four observations of the market, not a hundred.

### 3.5 Tuning guardrail

- **At most 3 parameter variants per version** on historical data, **all reported, losers
  included.** Variants are declared before any result is viewed.
- The chosen variant becomes **a new version** that must pass **forward, on unseen data**.
- **Historical results never prove a tuned version.** A replay can kill a version; it cannot
  promote one.
- Every card carries a **LIFETIME TRIES COUNTER**: variants run across *all* versions, ever.
  It only goes up. QUERY's verdict states it.

### 3.6 Price source

Every return figure names its price source (e.g. "yfinance daily, raw OHLC, pulled
2026-10-09"). Historical replays use **yfinance** (no key). The hub's UW bar path caps at 2
years and is not a replay source.

## 4 · Controls: every test reports one

A result without a control is not reported. Pick the ones that isolate *the claimed edge*:

| control | isolates | use when |
|---|---|---|
| **same tickers, all eligible days** | timing vs. just owning the universe | always |
| **ablation**: the trigger with one component removed | whether that component adds anything | the strategy has a multi-part trigger |
| **same date, cross-section**: all eligible universe names on each fire date | stock selection vs. the day | always for daily scans |
| **SPY over the same windows** | already in r_adj; report SPY's raw mean alongside | always |

Further requirements:

- **Split by regime.** At minimum SPY above / below its 200-day; the 3-state regime of §6.2
  where n allows.
- **Survivorship (§4.6).** Use a point-in-time universe, or state the caveat *and* run an
  ETF-only (or sector-ETF) subset as the survivorship-free check.

## 5 · Two stages

1. **Stage 1:** the market-adjusted stock return (§3).
2. **Stage 2:** the options expression, through `scripts/stage2_options_backtest.py`.
   Prefer a structure that isn't net long vega (shares, or a credit spread on the signal's side)
   unless the strategy's thesis *is* a vol expansion.

**SURFACE needs both.** Precedent: RSI-2 passed stage 1 and failed stage 2 on vega.

## 6 · The coverage grid and bucket ceilings

### 6.1 The grid (principal decision 2026-10-09)

Coverage, not equal counts. Every regime needs at least one live, graded long and one live,
graded short:

|  | LONG | SHORT |
|---|---|---|
| **WITH-TREND** | | |
| **CONFIRMED TURN** | | |
| **BEFORE THE TURN** | | |

**Confirmed turn** (09-23 definition): a daily close through the 50-day average, the average
stack turning, and volume confirming.

### 6.2 Market state at fire (census and regime splits)

- SPY ADX(14) **< 20** → **range**
- ADX(14) **≥ 25** with the average stack aligned → **trend**
- anything else → **transition**

### 6.3 Bucket ceilings: every card states the one that applies

| strategy kind | ceiling |
|---|---|
| BEFORE-THE-TURN | **B3 or TAIL only.** Short side carries the no-fly flag *"entering parabolic shorts too early"*. |
| FLOW-ORIGINATED | **B3** (with a PYTHIA value-area trigger) or **TAIL**. **B2 only** after a registered forward pass *and* a SPINE ruling citing it. **B1 never.** |
| other | stated on the card, with the ruling that sets it |

## 7 · Cards: the signal registry, version 0

`docs/strategies/<name>.md`, one per strategy (09-23 item S1). Committed. Every fact taken
from code cites `file:line`, verified by reading the line, never from memory or an older doc.

```markdown
# <NAME> (working name if the principal hasn't named it)

| field | value |
|---|---|
| signal_type / strategy keys | |
| emitting code | file:line |
| side | LONG / SHORT / BOTH |
| grid cell | WITH-TREND / CONFIRMED TURN / BEFORE THE TURN × side |
| incumbent it would replace | |
| schedule / trigger | cron + file:line, or webhook source |
| status | LIVE / SHADOW / SUPPRESSED / BROKEN / RETIRED, with the source line |
| bucket ceiling | per §6.3, with its basis |
| lifetime tries counter | N |

## Rules as approved
(source doc + date)
## Rules as coded
(file:line for each rule)
## Where they differ
## Evidence so far
(each figure: adjusted + raw, n, n dates, control, price source, artifact path + sha256)
## Kill rule
## Change log
```

## 8 · Hard rules (R-IV.823(b), R-IV.826(b))

1. **Branches only**, named `claude/lab-<topic>`. Never push `main`. Rebase on `origin/main`
   before pushing; report branch + commit. BUILD merges and deploys.
2. **LAB never grades its own registered test.** QUERY does.
3. **SEAL.** Never read or print anything that isolates rows with **`id ≤ 377783 AND
   fired_at ≥ 2026-08-17`** (the Triton holdout). Both predicates, always. That includes
   counts.
4. **Triton** is under a registered forward test until read 7 (Fri 2026-11-06). Don't change its
   code paths or read its outcomes. The only exception is the dark-pool collection (R-IV.823(e)).
5. **No secrets.** This folder holds no `.env`, API key or DB password, by design. Never
   print an env value. Never copy one in. Anything needing the UW key runs on Railway after
   BUILD merges.
6. **Results** go to `C:\temp\cc-query-handoff\lab\` with a sha256, and **are never committed**.
   The skill, cards and registrations are committed.
7. **Every test reports a control; every return figure states its price source.**
8. **Database:** aggregate counts only (`COUNT` / `GROUP BY`), through the **read-only
   postgres MCP** only, on non-Triton tables, **SQL printed verbatim** in the report (E1 to
   R-IV.552(b)). Never a `triton_*` table, never row-level output. If the MCP isn't available,
   say so. Don't work around it.
9. **At most 2 tasks in flight.** Report as each finishes.
10. **Acknowledge every block by number** and chase missing ones.
11. **Python:** LAB's own venv inside `C:\trading-hub-lab` (e.g. `.venv-lab`). Never
    `C:\trading-hub`'s `.venv-test`. Never work in `C:\trading-hub`.
12. Commits are pathspec-scoped, credential-pattern-scanned before staging (PROJECT_RULES.md,
    Workflow Rules). The repo is **PUBLIC**.

## 9 · Result artifacts

Staged to `C:\temp\cc-query-handoff\lab\<topic>\`. Each carries at its head: the ruling it
answers, the code commit, the price source and pull date, the declared variants (all of them),
the controls, and the lifetime tries counter. sha256 in bash, re-verified in PowerShell, both
quoted in the report.

## Change log

- 2026-10-09: v0, from R-IV.823(d) as amended by R-IV.826. Interpretation for SPINE to
  confirm: β is estimated on adjusted-close daily returns (split safety) while r and r_SPY stay
  on raw prices (§3.3).
