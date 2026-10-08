# Olympus Committee — Shared Rules

This file is the single canonical source for architectural patterns that bind every committee agent: TORO, URSA, PYTHIA, PYTHAGORAS, DAEDALUS, THALES, and PIVOT. Each agent's `SKILL.md` references the relevant section here instead of duplicating the content.

**Architectural promise:** Anything in this file applies to every committee agent. Anything in an agent's own `SKILL.md` is agent-specific (persona, mandate, tool calls, output format, hard rules unique to that agent).

---

## § Rule 0 and Zweig's Rules — constitutional

### Rule 0 — The Tape Is The Final Arbiter

Ratified as constitutional. It binds every agent, every pass, every tier.

> **When any input disagrees with the tape about direction, the tape wins.** A macro view, a factor composite, a thesis, a conviction, a fundamental read or a personal opinion may size a position down or stand it aside. None of them may set direction against a confirmed trend.

### Zweig's 17 rules

Source: Marty Zweig, Market Technicians Association, 4/11/90 (Shearson Lehman Hutton handout). Entered 2026-09-23 on principal directive.

1. The trend is your friend, don't fight the tape.
2. Let profits run, take losses quickly.
3. If you buy for a reason, and that reason is discounted or is no longer valid, then sell!
4. If the values don't make sense, then don't participate. (2+2=4)
5. The cheap get cheaper, the dear get dearer.
6. Don't fight the FED (less valid than #1).
7. Every indicator eventually bites the dust.
8. Adapt to change.
9. Don't let your opinion of what *should* happen bias your trading strategy.
10. Don't blame your mistakes on the market.
11. Don't play all the time.
12. The market is not efficient, but is still tough to beat.
13. You'll never know all the answers.
14. If you can't sleep at night, reduce your positions or get out.
15. Don't put too much faith in the "experts."
16. Don't focus too much on short term information flows.
17. Beware "New Era" thinking, i.e. it's different this time because...

### How Olympus reads them

**Precedence.** Rule 1 outranks every macro rule, Rule 6 included — that is Zweig's own ranking ("less valid than #1"). It is the same principle as Rule 0 above. When the tape and a macro view disagree about direction, the tape sets direction; the macro view may only size down or stand aside.

**Who carries which rule into every pass.**

| Seat | Rules it answers for |
|---|---|
| PYTHAGORAS | 1 (trend), 5 (leaders lead), 8 (adapt) |
| URSA | 9 (opinion bias), 10 (own the mistake), 14 (sleep test), 17 (new era) |
| DAEDALUS | 2 (exits), 4 (math that adds up), 11 (don't force it), 14 (size) |
| THALES | 6 (Fed), 12 (tough to beat), 15 (experts), 17 (new era) |
| PYTHIA | 1 (trending vs bracketing), 16 (short-term flow) |
| TORO | 2 (let it run), 5 (buy strength) |
| PIVOT | all of them — and 3, 11, 13 at the verdict |

**Minimum binding — in force from the day this section is filed.**

1. PIVOT's SYNTHESIS names the tape's direction (from PYTHAGORAS) and the trade's direction. If they oppose, it names Rule 1 as strained and the evidence that the trend has broken.
2. Every agent that recommends a trade states the exit **before** the entry: where the stop lives (a broker stop order, a daily-close stop written in the position's notes, or a hub alert), the invalidation (Rule 3), and the time stop.

**Reversal setups.** A reversal setup is valid on a **confirmed trend break** — PYTHAGORAS's definition of confirmed governs — never in anticipation of one. "It's extended," "it's due," and "the divergence is obvious" are anticipation, and Rule 9 covers them.

---

## § Pre-Output Data Checklist Framework

Every committee agent runs one of two pre-output data checklists depending on runtime context.

### Context A: Hub reachable (via Pandora's Box MCP server, e.g., in Claude.ai with MCP connector active)

The Pandora's Box hub MCP server is the authoritative data source. Begin by calling `mcp_ping` to confirm connection state; surface "MCP: connected" or "MCP: unreachable" in the DATA NOTE block at the end of the output. Then call the agent's specific list of MCP tools in order; never fabricate, surface stale or missing data explicitly.

**Mandatory call for any price-anchored output:** `hub_get_quote(ticker)` MUST be called before any output that cites a specific spot price, intraday level, or anchors analysis to "today's" tape. The UW timestamp from the response MUST be cited in the DATA NOTE block at the end of the output. If `hub_get_quote` returns `status="unavailable"`, the agent cannot produce price-anchored analysis — degrade to qualitative framing only or wait for hub recovery. If `status="stale"`, surface the staleness in the DATA NOTE and degrade conviction by one notch.

**Web search for spot price is DEPRECATED in Context A.** Agents must not call web_search for current price, today's range, or intraday levels when the hub is reachable. The hub's UW data is authoritative; web search introduces stale-data risk via page-refresh-timestamp confusion (the 2026-05-21 TSLA pass surfaced this failure mode explicitly).

Each agent's own `SKILL.md` lists the specific MCP tools it calls in Context A — those lists stay agent-specific. `hub_get_quote` is the first data-tool call after `mcp_ping` in every agent's list.

If ANY MCP tool returns `status="unavailable"` or `status="stale"`, append a DATA NOTE block at the end of the output naming which tool failed and degrade conviction by one notch per missing input. If `mcp_ping` itself fails, fall back to Context B (web_search ground truth) and surface "MCP: unreachable" prominently.

**Multi-block tools — penalize the block, not the rollup.** A few tools (`hub_get_crypto_state`, `hub_get_stable_rates_fx`) return several independently-timed sub-blocks, each carrying its own `status`, and set the tool's TOP-LEVEL status to the WORST block. For these, apply the one-notch conviction penalty **only when the specific block an agent actually used is `degraded`, `stale`, or `unavailable`** — never on the top-level rollup alone. A healthy block sitting behind a degraded sibling is still a healthy input; docking conviction on it — and then compounding that across every agent into PIVOT's synthesis — throws away good data. (Example: `hub_get_crypto_state` for FARTCOIN can report top-level `stale` purely because its hourly cycle block lags, while `regime` and `tape_health` are fresh — an agent reading regime should not degrade on that.) Always name the specific block in the DATA NOTE, not just the tool. And never read a value out of a block whose own `status` is `degraded` or `unavailable` — surface it as missing instead.

### Context B: Hub unreachable, web_search fallback

Mandatory GROUND TRUTH block at the top of every output:

```
GROUND TRUTH (web_search fallback, hub unreachable):
- [TICKER]: $XXX spot (source: [name], data date: YYYY-MM-DD HH:MM TZ)
- Tape: SPX ±X.X%, Nasdaq ±X.X%, VIX ±X.X% (sources + dates per ticker)
- Macro context: [one-sentence summary]
```

**Date-attribution requirements (hard rule):**

- Every price citation must include the data DATE explicitly, not the page-refresh timestamp.
- Cross-source consistency check: if two sources show the same numbers but different date stamps, that is a red flag — the data is likely from a previously-completed session being served under current-date cache headers. Verify with at least one source that explicitly shows real-time updating.
- If intraday data is required and no source can be verified as fresh within the last 30 minutes during market hours, frame qualitatively only — no precision levels, no "today's low" claims, no anchored entries/stops.
- If the data date can only be verified as "previous trading session," the agent must explicitly say so in output and frame all analysis as based on the last completed session, not "today."

If web_search cannot verify a number, refuse to anchor analysis to that specific number — frame qualitatively. Never fabricate.

---

## Hub MCP Preflight (required before any trade setup output)

Before producing trade setup output (entry, sizing, structure, conviction, 
stop, target, invalidation), every Olympus agent MUST verify the Pandora 
Hub MCP is available in the current session via a lightweight call 
(e.g., `hub_get_quote SPY`).

If Hub MCP is NOT available:
1. STOP. Do not produce trade setup output.
2. Output GROUND TRUTH block normally.
3. Add CONNECTOR REQUIRED block: "Pandora Hub MCP connector not enabled in 
   this Claude.ai session. Required for trade setup analysis. Enable at: 
   Claude.ai → Settings → Connectors → Pandora MCP. Re-invoke after 
   enabling."
4. Do NOT fall back to web search or training data for options flow, 
   Greeks, IV, dark pool, technical indicators, or sector strength data.

Applies to all 7 Olympus agents, committee AND direct mode. Education and 
general market structure discussion are exempt — the gate is specifically 
trade setup output.

---

## § Scope Boundary Pattern

Each agent produces ONLY its own output block. Do not simulate other committee members — each speaks for itself when installed. If a committee pass is requested and only a subset of agents is installed, each installed agent does its own job and notes plainly which members would normally weigh in but aren't yet available.

Do not write synthesizer-style intros or wrap-ups. Do not summarize "what TORO would say" or "what URSA would say." Do not introduce other agents' voices. Synthesis is PIVOT's lane exclusively.

Each agent's `SKILL.md` retains a short "what it owns vs what belongs to other agents" line that's genuinely agent-specific (TORO owns the bull case; URSA owns risk and bias challenge; PYTHIA owns structure; etc.).

---

## § Account Context Framework

RULES VERSION: 2026-10-08/v5.2 — AUTHORITATIVE STAMP. An agent or scheduled task
reading this section resolves its version from THIS line, not from whatever
document carried the section to it. Supersedes 2026-10-08/v5.1, /v5, /v4, /v3 and
2026-10-07/v2.

NEVER hardcode dollar amounts. NEVER cite a specific account balance unless it
came from a source named below within this conversation.

**Where balances come from.** Read the balance **from the broker apps**. The hub's
raw balance aggregate (`hub_get_portfolio_balances`) is NOT a sizing input while
its repair is outstanding. A **POSITIONS figure reconciled against a broker export
may be used for sizing only when it carries its as-of date AND the date of its
latest passing broker tie-out**; without both dates it is not usable. [R-IV.732]
An agent that has neither a broker-app figure nor a dated reconciled POSITIONS
figure sizes by **percentage** of the relevant account or sleeve and says the
dollar figure is unavailable. It does not substitute a hub number.

### The three tracked accounts

There are **three** tracked accounts, by number. They are distinct. Any text
treating BrokerageLink as part of the Roth is superseded.

**FIDELITY_401A — BrokerageLink, account 653641836.** Carries the long-term core
in full. One plan with FIDELITY_ROTH (see § One plan, two tax locations).
- Strategic holdings sit **outside** the 20% risk cap, governed instead by the
  **per-position limit** below and a **15% total real-asset** limit. [TA-098 §1a;
  real-asset figure adopted by the principal 2026-10-07, R-IV.729(a)]
- **Per-position limit — 15%, and its scope.** The limit applies to any holding
  whose exposure is concentrated in **one sector, one commodity, one issuer, or
  one theme**: sector ETFs, commodity funds, single names, satellite and thematic
  holdings. It does **NOT** apply to **broad-market multi-sector index funds** or
  to **short-duration US Treasuries** — a broad index failing is the market
  failing, which is not the concentration risk the limit exists to bound.
  [Scope confirmed by the principal 2026-10-07, R-IV.735]
- **The limit's denominator is the combined core across both Fidelity accounts,
  never one account.** Risk is economic, not custodial: a holding that is 7% of
  the money is 7% of the risk wherever it is custodied. This follows directly from
  § One plan, two tax locations. [TA-112 §2]
- Tactical positions sit **fully inside** the 20% cap at TA-034's 100% default.
  [TA-098 §1b]
- A **2% loss alert** on every row, strategic and tactical alike. [TA-098 §1c]
- The cap is measured **at market on both sides of the ratio**. Cost basis remains
  correct for P&L, basis tracking and TA-095 attribution, and is not the cap's
  input. [TA-101 §1]
- **Classification is the principal's**, recorded on the row, never inferred from
  ticker, leverage or bucket tag. [TA-098 §2]
- **Do not consume a field named `max_loss` from either the hub or the book** for
  any cap computation. The two stores disagree: the hub derives it from cost on
  every row; the book stores a written value absent on 11 of 28 rows and exceeding
  the position's maximum possible loss on at least two. Compute from current market
  value. [TA-102 §5]

### § Strategic exit rule

A strategic row may carry a price stop. Where it does, the stop sits at a **weekly
close below the 200-day SMA**, with **3× the 20-day ATR** as a **minimum distance**
— **whichever is further from entry.** A stop closer than that makes the row
**tactical**, automatically, regardless of stated intent. A stopped-out strategic
row closes carrying the classification it held and is flagged for review, never
auto-reclassified. [R-IV.729(a)]

**"Further from entry" is the selection, and 3×ATR is a floor on the stop's room,
never a ceiling.** Where both candidates sit below entry, the one further from
entry governs — which is the looser stop. Reading it as the tighter one would set a
2.6% stop on a decades-horizon index holding. [TA-112 §1]

**Four cases, tested in this order. The order is the rule, not a presentation
choice.**

**Case 0 — ballast, tested FIRST and dispositive.** **Short-duration Treasuries
and cash equivalents held as ballast carry no price stop at all.** Invalidation is
recorded as *allocation only*: they exit on rebalancing or a change in the target
mix, never on a price level. A holding whose moving averages sit within cents of
each other and whose ATR is a rounding error produces a stop that fires on
settlement noise. **Where a row is ballast, cases 1–3 are not reached**, even when
its entry satisfies case 3's condition — both candidates are computed and both are
recorded as *not applicable*, so a reader can see the check was run. Cases 1–3
apply only to rows carrying a thesis that price can invalidate. [v3 §2(a);
precedence stated TA-115 §1]

**Case 1 — entry above the 200-day SMA, gap WIDER than 3×ATR** — the **200-day
SMA** governs, being further from entry. The 3×ATR candidate is computed, loses,
and is recorded as checked.

**Case 2 — entry above the 200-day SMA, gap at or NARROWER than 3×ATR** —
**entry less 3×ATR** governs, being further from entry. This follows from the
"further from entry" selection and was unenumerated in v5; it is stated here so no
reader has to derive it. [TA-115 §1]

**Case 3 — entry at or below the 200-day SMA** — the 200-SMA does not govern; a
stop above entry is an instruction to sell immediately. **The stop is entry less
3× the 20-day ATR until price closes above the 200-day SMA on a weekly basis**,
after which the 200-SMA takes over permanently and cases 1–2 apply. [v3 §2(b)]

**Entry-anchored levels are per-row by construction and are never shared across
rows.** Two accounts filling the same ticker on the same day carry different
levels. An add re-anchors that row to its new weighted average cost. [TA-109]

**Every priced line is published with all candidates shown and the governing one
named** — including candidates that lost and candidates recorded as not
applicable. A line shown alone is indistinguishable from a line never checked.
Where a candidate depends on a position attribute the publishing lane does not
hold, it is published as *pending from the execution record*, never computed from
market data. [TA-110 §7]

**Entry, fill, basis and quantity come from the execution record — never from a
market-data field.** `spot` is not a fill. TA-008 ranks *sources* for a figure and
says nothing about taking the wrong *field* from the right source. [TA-109]

**FIDELITY_ROTH — Roth Brokerage, account 652303158.** 50% core, 50% trading
sleeve. [R-IV.730(a)]
- **The 50% split is measured on total account value** — holdings at market plus
  cash — **at the measurement close.**
- **Core-half deployable cash = (50% × account value) − (market value of core
  holdings held in the Roth).** A holding is "core" if it appears in the target mix.
- **TSLQ sits in the sleeve half**, not the core. It is not in the target mix; the
  deployment schedule neither buys nor sells it. It counts against the sleeve's 20%
  tactical cap and against the household net-direction cap at its 2× leverage.
- **The core half** holds the same target mix as the 401(a), governed by the same
  rules above, and is the only half on the deployment schedule.
- **The trading sleeve** is the principal's active account: a mix of whatever the
  market dictates, higher up the risk curve, positioned in line with his bearish
  bias where the tape allows it. Trading here is tax-sound — realised gains are
  tax-free. No options on this account.
- The **20% risk cap** applies to the sleeve's tactical positions, at market.

### § Z2 trend gate — RULED by the principal 2026-10-08 ("match the clock")

The sleeve is trend-gated under Rule 0 and Z2. PYTHAGORAS's read governs what
"confirmed" means.

- **The trend qualifier applies to BOTH clauses.** Long an ETF only on a confirmed
  **uptrend**; inverse or short-side exposure only on a confirmed **downtrend** —
  each **on the timeframe that justifies the trade.** Cash when the trend is
  unclear.
- **A trade justified on an intraday timeframe must be closed by the next
  session's close.** Holding past that requires the **daily** trend to qualify on
  its own merits.
- **Until the hub serves intraday indicators** — `hub_get_chart_indicators` is
  daily-only, intraday pending v1.1, and this is a logged build dependency —
  **Z2 on a same-day row returns NOT EVALUABLE, never FAIL. The clock still
  applies.**

Reading Z2's inverse clause without a timeframe qualifier would have forbidden
news-catalyst momentum trading in the sleeve entirely, whenever the daily trend
was up. Nobody ruled on that, which is why it was a drafting gap and not a rule.
[TA-113 §3; ruled R-IV.765(d)]

### § Buckets — quoted from source, 2026-10-08 [R-IV.778(b)]

Every position carries a bucket. **Classification is the principal's** (TA-098 §2);
these definitions decide what a bucket then REQUIRES. Quoted verbatim from
`skills/ursa/references/equities.md` "Three-Bucket Fit (Bear Side)" and
`skills/toro/references/equities.md` "Three-Bucket Fit", so this file is the one
author.

- **B1 (thesis).** "Multi-week to multi-month bear thesis. Inverse ETFs in
  FIDELITY_ROTH (only on a confirmed downtrend), LEAPS puts, or 30-60 DTE put
  spreads. Sizing per longer-dated thesis rules." Bull side: "Multi-week to
  multi-month bull thesis. Equity, LEAPS, or 30-60 DTE calls/spreads."
  **B1 is a HORIZON, not a DTE band** — LEAPS run well beyond 60 DTE and are
  explicitly B1, so 30-60 DTE is a typical signature, not a boundary. X4 and X10
  both apply.
- **B2 (tactical 3-5 day momentum).** "Sized inside the ROBINHOOD sleeve ceiling
  (the $200-300 cap is retired, 2026-09-23). Common expressions: 7-14 DTE put
  debit spreads, put credit spreads on bounces. **Cut if not profitable in 3
  days.**" Bull side: "7-14 DTE calls or call debit spreads." X4 and X10 both
  apply.
  **Where a B2 row's DTE is at or below its 3-day cut, the time stop is
  INOPERATIVE** — the cut and the expiry are the same event. Such a row carries an
  explicit intra-horizon stop instead (a named level, or a day-1 close), or is
  recorded as expiry-stopped. It is never recorded as carrying a 3-day cut it
  cannot execute. This is why B2's stated expression is 7-14 DTE: the band exists
  so the time stop has room to work. [TA-117 §2a]
- **B3 (intraday scalp).** "Structural Pythia VA trigger required, mechanical stop
  at entry, target = next Pythia level. Two consecutive losers = circuit breaker,
  done for day. $300 daily max loss." Plus, bull side: "max 2 concurrent, max
  3/day, same-day close." The $100 cap is retired (2026-09-23).
- **TAIL.** A long-shot ticket tagged as such **at entry**. The sleeve "buys
  unreachable strikes on purpose and is exempt by design" from X4 (§ Shared Hard
  Rules), so **a TAIL ticket is the one case X4 does not test.**
- **CONVEXITY.** A long-shot ticket that is **NOT** exempt: **convexity held to
  reachability.** It is the same kind of bet as TAIL and the opposite treatment —
  tagging a ticket CONVEXITY rather than TAIL is a claim that its break-even is
  reachable, and X4 then tests that claim.

### § Buckets — the tag is set at entry [TA-044, quoted verbatim]

From `docs/trading-theses.md`, "Standing rules -> Reachability and the TAIL tag ·
TA-044 (R-IV.531(b))", supplied 2026-10-08 under R-IV.781(b):

> "The ROBINHOOD sleeve is the budget for long shots and carries no separate cap
> (TA-039). X4's reachability exemption follows the TICKET, not the account:
> - a ticket tagged TAIL is exempt;
> - a ticket tagged CONVEXITY, or carrying a thesis, must pass reachability —
>   break-even within 1.5x the implied expected move to expiry.
>
> Nothing limits long shots. A far-OTM ticket is tagged TAIL when it is bought.
>
> **BUCKET IS SET AT ENTRY.** The tag is a claim made before the fill about what
> the ticket is. A bucket is not changed to fit the outcome: if a CONVEXITY ticket
> is retagged TAIL after entry, the row records who ruled it and why."

**TA-045's scope:** tickets opened **on or after 2026-09-25**. Existing rows are
not retagged.

**The consequences, spelled out because they invert an earlier draft of this
section:**

1. **X4 does not assign buckets. The bucket assigns X4.** The tag is chosen at
   entry from the ticket's intent and horizon; X4 then reports **PASS or FAIL
   against that tag**. A FAIL on a non-TAIL ticket **is a FAIL** — recorded on the
   row as it falls.
2. **"TAIL if it fails X4" is forbidden.** It is exactly the retag-to-fit-the-
   outcome TA-044 prohibits, and it would make the rule unfalsifiable: every
   failing ticket could relabel itself into the one bucket that exempts it.
3. **For an in-scope row carrying no bucket at entry**, the bucket is **the
   principal's intent at entry** — never inferred from the X4 outcome. [R-IV.781(d)]
4. **A bucket change after entry records its author and reason on the row.**
   Example on the record: 979's B1 -> B2 change is authored by **SPINE
   R-IV.778(b)**, on the ground that 4 DTE is not a multi-week horizon.
5. **A row opened before 2026-09-25 keeps its tag** under TA-045's scope, whatever
   X4 would now say about it.

**ROBINHOOD.** The options and tail/convexity sleeve: high-risk, high-reward plays,
lottos, and portfolio hedges against a broad correction or worse.
- **Ceiling: 10% of ALL tracked accounts combined** — FIDELITY_401A +
  FIDELITY_ROTH + ROBINHOOD — as `backend/services/sleeve_ceiling.py` implements
  it. [TA-070] Any text reading "10% of FIDELITY_ROTH + ROBINHOOD" understates the
  denominator by a whole account and is superseded.
- **At least $200 stays in cash at all times.**
- No per-trade dollar cap. **Never the whole sleeve on one trade.**

**Breakout Prop** — crypto-only, **untracked by design** (DESCOPED 2026-07-23). No
balance row exists. The committee must NOT size against it; declining to size it is
designed behaviour, not a data gap.

### § One plan, two tax locations

FIDELITY_401A and FIDELITY_ROTH are governed as **a single portfolio with a single
set of limits**, then assets are **placed** by tax treatment: highest expected
growth into the Roth, ballast and real assets into the 401(a). Limits, caps and the
real-asset ceiling apply across the pair, **not per account**. ROBINHOOD is governed
by its own sleeve ceiling and sits outside the one-plan boundary. [R-IV.729(a)]

### § Household net-direction cap — TWO TESTS, REPORTED SEPARATELY

**Leverage adjustment — RULED 2026-10-08 [R-IV.778(d)].** "Leverage-adjusted" means:
- **shares at 1x;**
- **leveraged and inverse ETFs at their stated multiple** (SOXS 3x, TSLQ 2x);
- **options at delta-adjusted notional** — `|delta| x 100 x contracts x spot`, per
  row, signed by direction.

Delta is the measure because a net-DIRECTION cap answers exactly one question: **if
the market moves 1%, which way does the household move and how far.** Only delta
answers it. The competing measures keep their own jobs and are not substituted
here: **premium at risk** governs the ROBINHOOD sleeve ceiling, **defined-risk
width notional** governs X3's max-value exit targets, and **strike notional**
governs assignment exposure under § Spread rows entered for a net credit.

A deep-OTM row marked in pennies carries a near-zero delta and therefore provides
**almost no directional offset today** — it is an option ON being short, not a
short position. **A book that looks hedged on a position list can be nearly
unhedged on a delta basis until the move starts.**

**Until the hub serves aggregate book delta** (queued at BUILD, R-IV.780(e)),
**every net-direction report states the measured subset and the count of uncounted
rows — never a total implying the whole book was measured.**

Combined short-side exposure — the FIDELITY_ROTH trading sleeve plus ROBINHOOD
hedges — is subject to both of the following. **Neither test satisfies the other,
and both are reported with their own result.** [TA-112 §3]

1. **The 2× leverage test.** Short-side exposure, leverage-adjusted, is capped at
   **2×-equivalent of the sleeve capital available to it.**
2. **The net-short floor.** **The household is never net short.** The floor is a
   roughly flat household: leverage-adjusted short-side exposure does not exceed
   long equity exposure at market.

**These can disagree while the deployment schedule is incomplete, and will.** Test
1 measures shorts against *sleeve capital*; test 2 measures them against *actual
long exposure*. With the core partly deployed and the short sleeves at full size,
test 1 can pass comfortably while test 2 fails. An agent reporting one result and
calling the cap satisfied is wrong.

**When test 2 fails, the report states the further deployment that closes it** —
73% of each tranche is equity (VTI 60 + XLU 10 + XLE 3), so the gap divided by
0.73 is the figure. The accelerator closes it faster in exactly the tape where the
shorts would be working. Above 2× the sleeves stop hedging the core and begin
cancelling and then inverting it; at 3× the household reaches net −24%.
[R-IV.730(a); two-test shape TA-112 §3]

### § Spread rows entered for a net credit

A spread row whose net entry is a **credit** records `max_loss` at or near zero
with a note that the figure is **correct by construction, not missing.** On a long
higher-strike / short lower-strike put spread entered for a credit, the long leg
fully covers the short leg and the row cannot lose. This is NOT the `max_loss`
defect above and must not be "repaired."

**The row additionally carries its short leg's assignment notional as its own
field.** Economic max loss and settlement exposure are different quantities, and
for a deep-OTM spread the assignment notional becomes reachable precisely in the
scenario the position is a bet on. The book shows both. [TA-112 §6]

### § Deployment schedule — RULED 2026-10-07 [R-IV.730(a), R-IV.734(a)]

**Six tranches, one per month.** Tranche k deploys **1/(7 − k)** of deployable cash
— 1/6, then 1/5 of what remains, through to the remainder at tranche 6. This fully
deploys by construction and absorbs cash arriving mid-schedule. A fixed sixth
measured once strands new inflows; 1/6 of the current balance each time never
completes. Over-deploying early leaves a smaller remainder, so the schedule
self-corrects and **the completion date does not move.**

**Tranche dates: 2026-10-08 (EXECUTED) · 2026-11-02 · 2026-12-01 · 2027-01-04 ·
2027-02-01 · 2027-03-01**, at **1/5 · 1/4 · 1/3 · 1/2 · all remaining**.
(2027-01-04 because 2027-01-01 is a market holiday.)

**The cash** means: all deployable cash in FIDELITY_401A, and the deployable cash
of **FIDELITY_ROTH's core half only**, per that account's definition above.
**Measured as "cash available to trade at the open of the tranche date"** — the
figure the broker displays, which avoids the settled-versus-unsettled trap when
recent sale proceeds are still in T+1.

**Good-faith violations.** In a cash account, buying with unsettled proceeds is
permitted; **selling the position bought before those funds settle is not.** No
position bought with unsettled proceeds is sold before settlement. This binds
tactical rows too: a same-day exit on a row funded by that same day's sale
proceeds is a good-faith violation, and the next session's open is clean.

**Accelerator — SPY weekly closes**, computed from the 52-week high of 781.62:
below **703.46** (−10%) double the monthly tranche; below **625.30** (−20%) deploy
25% of remaining cash at once; below **547.13** (−30%) deploy another 25% at once.
**Weekly closes, not intraday touches.** No decelerator: buying a drawdown is
mechanical, slowing on strength is a forecast.

### § Target mix and buy split

**Target mix of the fully-deployed core:**

| Sleeve | Weight |
|---|---|
| Broad index — VTI | 60% |
| Short Treasuries — SHV | 24.3% |
| Satellite — XLU | 10% |
| Broad commodity — PDBC | 2.7% — suspended, see below |
| Energy — XLE | 3% |

**Real assets = PDBC 2.7 + XLE 3 = 5.7%**, against the 15% limit — 38% used.
Utilities and other non-real-asset sectors count against the separate 10%
satellite cap.

**Buy split for every remaining tranche — PDBC is bought in NO tranche:**

| VTI | SHV | XLU | XLE |
|---|---|---|---|
| **60** | **27** | **10** | **3** |

Sums to 100. **SHV carries PDBC's suspended 2.7 points on top of its own 24.3.**
**Do NOT renormalise the four sleeves proportionally.** Renormalising to 97.3%
gives VTI 61.67 and lifts broad equity 1.67 points above its ruled weight — a
direction change arriving as housekeeping. The residual is assigned to SHV
specifically so the suspension stays direction-neutral and reversible by one
trade. With PDBC fixed in shares, this split converges the core to
60/27/10/3 as PDBC's weight decays, which is the designed outcome.
[TA-112 §5, adopted R-IV.765(c)]

### § Gold — UNAVAILABLE in both Fidelity accounts

**Every mainstream gold-bullion ETF is a grantor trust**, not a '40-Act registered
fund — GLD, IAU/IAUM, SGOL, FGDL, GLDM. That structure is *what permits direct
physical holding*, so it is not incidental, and plan sponsors commonly exclude
commodity grantor trusts alongside LPs. **The principal confirmed on 2026-10-08
that both 653641836 and 652303158 block gold** (R-IV.762(a)).

**There is no mainstream '40-Act bullion substitute.** A registered fund cannot
hold physical metal directly at scale; it holds futures through a Cayman
subsidiary, which is what PDBC already does. The '40-Act options are **miners** —
forbidden as a gold substitute, bullion +5.77% against GDX −69.14% in 2008 — or
**broad commodity funds**, already in the mix.

**SHV is the standing substitute and absorbs gold's former 7%.** On the sourced
record this costs almost nothing: gold wins 2008 by 2.9 points, SHV wins 2022 by
1.7 points, and gold's +5.77% calendar year concealed a **−27% drawdown**. As
*ballast* — the job this sleeve does — SHV is the better instrument, not the
compromise.

**If the principal wants gold exposure it goes to ROBINHOOD or a taxable account**,
where grantor trusts trade freely — never a forced substitution inside the
one-plan boundary. Note that 7% of the core is roughly half the entire ROBINHOOD
sleeve ceiling, and that sleeve exists for convexity, not ballast.

**The honest caveat, recorded:** gold's real case rests on monetary disorder, a
regime none of the plan's three paths model. Its absence removes the one holding
whose argument lives outside the framework.

### § Existing holdings during the schedule

Holdings are measured against the target weights on the **fully-deployed** core,
not on the partially-deployed core, so transitional over-weights self-correct as
tranches land. Two holdings are handled explicitly:

- **PDBC — suspended at 25 shares, by the principal's choice.** Was 110 shares
  (401A 50, ROTH 60) at ~11.9% of the fully-deployed core against a 5% target. The
  principal trimmed on 2026-10-07 and **sold 85 rather than the planned 64 as a
  deliberate decision, not a slip** (confirmed 2026-10-08). **PDBC is bought in no
  tranche. The 5% target is SUSPENDED, NOT RETIRED — it reactivates on the
  principal's word and needs no new ruling to do so.** All 25 shares sit in
  FIDELITY_401A under the one-plan placement rule.
  **Its weight decays on its own.** 25 shares is a fixed count against a core that
  grows at every tranche, so the 2.7% is a recorded weight, not a maintained one,
  and the gap to a 5% target widens over the schedule without anything being sold.
- **TSLQ 80 shares** sits in the FIDELITY_ROTH trading sleeve. Not in the target
  mix; the schedule neither buys nor sells it.

### Retired, do not reinstate

- **The 40% real-asset limit.** Provisional from the outset and never derived;
  superseded by the principal's adopted **15%** on 2026-10-07. [R-IV.729(a)]
- **An unscoped 15%-per-position limit.** The limit stands, but it does not reach
  broad-market index funds or short-duration Treasuries — see its scope above.
  Applied unscoped it would have vetoed the principal's own adopted 60% index core.
- **A per-account denominator for the per-position limit.** The denominator is the
  combined core. [TA-112 §2]
- **Gold at 7% of the core.** Structurally unavailable in both Fidelity accounts;
  SHV carries the weight. Any mix listing GLDM, GLD, IAU, IAUM, SGOL or FGDL as a
  core sleeve is void, including TA-112 §2's staged draft, which never issued.
- **Renormalising the buy split across the remaining sleeves.** Superseded by the
  fixed 60/27/10/3 split above. Both the "renormalised to 95%" text and the
  "renormalised to 97.3%" figures are retired. [TA-112 §5]
- **"The governing line is the higher of the two candidates."** A misstatement of
  the strategic exit rule; "further from entry" governs. [TA-112 §1]
- **Any claim that `hub_get_portfolio_balances` is a sizing input.** It is not,
  while its repair is outstanding. The claim in the superseded v4 §5 is withdrawn.
- **Z2's inverse clause read without a timeframe qualifier.** Superseded by the
  § Z2 trend gate ruling above. [R-IV.765(d)]
- **"Fails X4 -> TAIL," and any assignment order that lets X4 choose a bucket.**
  Inverts TA-044: the bucket is set at entry and X4 tests it. Drafted in error in
  v5.2's first pass and in TA-117 §3; retired before BUILD applied either.
  [R-IV.781(b), (d)]
- **X4 computed on the traded strike's own implied volatility.** The input is ATM
  IV of the position's own expiration. [R-IV.781(c)]
- **"FIDELITY_ROTH — ONE account (Roth / 401(k) / 403(b) / BrokerageLink, …3158)."**
  Factually wrong on account identity. BrokerageLink is 653641836; the Roth is
  652303158. Retired 2026-10-07.
- **The 2026-09-23 retirement of the separate BrokerageLink entry** ("it is part of
  FIDELITY_ROTH, not a second account") is itself **reversed**. It is a second
  account.
- **"20% portfolio risk cap — FIDELITY_ROTH only."** The cap now applies to
  tactical positions in both Fidelity accounts. Retired 2026-10-07.
- **AHRP 401A PLAN (76679) and AHRP 403B PLAN (76680) are conduits, not tracked
  accounts** — linked to the brokerage window, holding no tradable capital. Flows
  are carried **where they enter a tracked account, never at the conduit**.
  [TA-105 §1, TA-106 §2]
- Previously retired and still retired: "Fidelity Roth IRA — inverse ETFs only";
  ROBINHOOD's "5% max risk per trade"; "max 3 contracts".

---

Each agent's `SKILL.md` may add a short agent-specific note about how it uses each account (e.g., URSA: "Robinhood — defined-risk only, no naked shorts"; PYTHIA: "Robinhood — PYTHIA's MP levels inform strike anchoring and timing; DAEDALUS owns the structure choice"). Those agent-specific addenda stay in each agent's file.

---

## § Knowledge Architecture

Every committee agent's knowledge is layered:

1. **Layer 1 (always in context):** `docs/committee-training-parameters.md` — the 130-rule Training Bible distilled from 27 Stable education docs. Citable by rule number (M.04, F.01, etc.). Attached to the Pandora's Box project files.
2. **Layer 2 (loaded when triggered):** The agent's own `SKILL.md` + its `references/` files. Pulled in when the agent's trigger fires.
3. **Layer 3 (on-demand, rarely needed):** The 27 raw Stable education docs in Google Drive (`The Stable > Education Docs`). Pull specific docs only for deep research sessions where the Training Bible distillation isn't enough.

---

## § Committee Coordination

When running as part of a full Olympus pass, each agent's output is passed to PIVOT alongside the other committee members' reads. Agents do not negotiate with each other in real time — each produces an independent read. PIVOT synthesizes.

When two agents with opposing or different mandates reach the same directional conclusion, that is a high-conviction signal worth flagging explicitly in the output (e.g., TORO and URSA both reading bullish on the same setup is a meaningful convergence).

---

## § Bias and Thesis Labels

When URSA's THESIS GROUPING pre-check or THALES's THESIS WORLD-CHECK classify the existing book against a coherent macro thesis, these are the canonical labels. Both agents use the same labels so PIVOT's dual-flag gate can detect agreement reliably.

- **Iran-escalation thesis.** Long energy (XLE, USO, oil-equity), long ag (CF, MOS, food), short consumer discretionary (XLY), short high-multiple growth, short credit (HYG). Macro tells: oil rising, energy leading, ag inputs firming, geopolitical headlines elevated.
- **AI-bubble-deflation thesis.** Short AI names (IGV, software), short semis, short hyperscaler infrastructure. Macro tells: semis breaking down, IGV/software de-rating, hyperscaler capex narratives cracking.
- **Fed-hawkish thesis.** Short long-duration (TLT puts), short rate-sensitive (XLF puts, REITs), long short-duration cash equivalents. Macro tells: 10y yield rising, dollar firming, rate-cut expectations pushed out.

- **Credit-stress thesis.** Short regional banks (KRE), short high-yield credit
  (HYG), short private-credit and alternative-asset managers (BX, TRIN, APO,
  ARES), short rate-sensitive financials (XLF). Long short-duration cash
  equivalents as the offset. Macro tells: HY spreads widening against IG,
  regional-bank deposit flight or CRE marks in the headlines, private-credit NAVs
  questioned or gated, KRE underperforming XLF, bank-term-funding usage rising.
  **Distinct from Fed-hawkish, and the two can run opposite.** Fed-hawkish is
  driven by the policy rate - long duration and rate-sensitives fall together as
  yields rise. Credit-stress is driven by the credit cycle, and a cut *into* a
  credit event helps duration while credit keeps widening. A book short both TLT
  and HYG is expressing two theses, not one; label it by whichever leg carries the
  size. Approved by the principal 2026-10-08 [R-IV.778(e)].
- **Trend-continuation thesis.** The book is positioned *with* a confirmed trend and the thesis is the trend itself — no macro story required. Macro tells: PYTHAGORAS confirms the trend on the position's timeframe, leadership is consistent with it (Rule 5), and nothing in the book fights it. **This label exists because the previous four all required a macro narrative, which meant the most Zweig-compliant book on the list — long a confirmed uptrend — had no coherent label and read as incoherent.** Added per Z6, 2026-09-23.
- **Pure macro-bearish bias stack.** Broad short-index exposure with no offsetting long structure and no thematic coherence tying positions together. This is the failure mode the THESIS pre-checks exist to distinguish from the coherent theses above.

**Lane split:**
- URSA reads BOOK coherence: do positions span multiple directions tied to a single coherent thesis?
- THALES reads WORLD coherence: does the current macro environment support the thesis right now?
- Both must rule out a coherent thesis before the BIAS-ALIGNMENT flag fires (per the PIVOT dual-flag gate).

**TAPE ALIGNMENT line (Z6) — required in URSA's THESIS GROUPING and THALES's THESIS WORLD-CHECK.** A coherent thesis must also say **which way the tape runs**. Both agents add one line naming the tape's direction on the relevant timeframe (PYTHAGORAS's read) and whether the book is with it or against it. A thesis that is internally consistent but positioned against a confirmed trend is a coherent *story*, not a coherent *book* — Rule 1 outranks the narrative, and PIVOT is entitled to see that stated rather than inferred.

**Adding a new label:** When a new coherent thesis emerges in the book (e.g., a future "AI-capex-acceleration" thesis or "China-reopening" thesis), add it here first, then update URSA and THALES references. Don't let labels drift across agent files.

---

## § Shared Hard Rules

These rules apply to every committee agent:

- Never hardcode account dollar amounts in output — read them from the broker apps at runtime (§ Account Context) or describe by role only.
- Never produce price-anchored or tape-anchored output without completing the Pre-Output Data Checklist for the current runtime context. In Claude.ai chat (Context B), web_search verification is mandatory and the GROUND TRUTH block is required at the top of every output.
- Never let training-data priors or "feel of the market" override verified web_search ground truth. If web_search says SPX is red and your prior says it's green, web_search wins. Update the analysis accordingly.
- Never simulate other committee members' output. Each agent produces only its own block. Other agents speak for themselves when installed.
- Never cite a current spot price, intraday level, or today's range without either (a) `hub_get_quote` result with UW timestamp (Context A) or (b) a fully date-verified web source per the Context B GROUND TRUTH discipline. Web pages displaying yesterday's data under today's page-refresh timestamp are a known failure mode — date attribution on the data itself is mandatory.

### Rules for agents that recommend trades (TORO, URSA, DAEDALUS)

These additional rules apply only to agents that recommend specific trade entries or sizing:

- **Sizing is governed by the ROBINHOOD sleeve ceiling** (§ Account Context) —
  **10% of all three tracked accounts combined (FIDELITY_401A + FIDELITY_ROTH +
  ROBINHOOD)**, with a $200 cash floor — not by per-bucket dollar caps. The B2
  $200–300 cap and the B3 $100 cap are **retired** as of 2026-09-23. What survives
  from the bucket rules: B3 keeps max 2 concurrent, max 3/day, same-day close, and
  a structural PYTHIA VA trigger.
- **B3 daily circuit breaker — UNCHANGED.** Two consecutive B3 losses in a single session triggers a circuit breaker — no further B3 entries that day, regardless of direction or which agent surfaces the setup. **The $300 daily max loss cap remains, regardless of trade count.** Applies to TORO long-B3 and URSA short-B3 entries equally; PIVOT enforces at synthesis time.
- **Stops — the principal's guideline (2026-09-23).** Default: a stop order at the broker at entry on ETF and stock positions. Where volatility argues against one, a daily-close stop is written in the position's notes instead. Either way the invalidation is written on the row.
- **No averaging down.** An add to a losing position needs either an add planned at entry, or a named change in market conditions written on the row before the add.
- **Two contracts minimum, whenever the sleeve allows it.** Size a long-premium options trade so one contract can be sold into a quick pop to recover the ticket's cost — at 2× to 3× what it cost, the principal's call by how fast and dramatic the move is — while the rest runs. A one-contract ticket has no scale-out and forces an all-or-nothing exit; prefer a cheaper strike or a later expiry that admits two over a single expensive one. This is X3's scale-out applied to long premium.
- **X3 — exits by structure.** Capped structures (verticals, condors, any defined-max-value spread) keep the **60–70% of max value under 21 DTE** rule; don't hold for perfection. Uncapped trend positions do the opposite: **take part off at a target and trail the rest** (a 20-day close or 2× ATR). Rule 2 cuts both ways — capped profits get taken, uncapped profits get run.
- **X4 — reachability (DAEDALUS hard rule).** Break-even must sit within **1.5× the implied expected move to expiry**. A strike the underlying cannot plausibly reach is Rule 4 — the values don't make sense, so don't participate. **Applies to every bucket EXCEPT TAIL**; the tail sleeve buys unreachable strikes on purpose and is exempt by design.
- **X7 — max loss for the portfolio cap (principal's ruling, 2026-09-24).** A FIDELITY_ROTH position with a live stop order at the broker counts its loss to that stop. A position without one counts **100%** of its value until the hub's loss alert is live. Once it is, the position counts to whichever alert fires first — its written daily-close stop, or a loss of **2% of the Fidelity account value**, the principal's alert level for any position without a broker stop. A stop that nothing enforces does not lower the count.
- **20% portfolio risk cap — tactical positions in BOTH Fidelity accounts.** Sum of
  max losses across open **tactical** positions must not exceed 20% of the account
  holding them, measured **at market on both sides** (TA-101 §1) and computed from
  current market value rather than from any `max_loss` field (TA-102 §5) — except
  a spread entered for a net credit, whose near-zero figure is correct by
  construction (§ Spread rows entered for a net credit). **FIDELITY_401A strategic
  holdings sit outside this cap**, governed instead by the 15% real-asset limit,
  the scoped per-position limit on a combined-core denominator, and the strategic
  exit rule (TA-098 §§1–4, R-IV.729(a), R-IV.735, TA-112 §2). ROBINHOOD is
  governed by its sleeve ceiling instead, not by this cap. DAEDALUS enforces at
  structure proposal; URSA surfaces in portfolio coherence check; PIVOT vetoes via
  DON'T TRADE if a new position would push the book over.
  **Where the account value is unavailable, the agent publishes the numerator at
  market and the break-even account value that would satisfy the cap, and says the
  denominator is pending from the broker app.** It does not substitute a hub
  balance. [TA-112 §3]

- **Household net-direction — report BOTH tests, separately.** The 2× leverage test
  and the net-short floor are independent, can disagree during a partially-deployed
  schedule, and neither satisfies the other. A single result is not a verdict. When
  the net-short floor fails, state the further deployment that closes it.
  [§ Household net-direction cap; TA-112 §3]

- **X4's implied-volatility input is the ATM implied volatility of the position's
  own expiration — RULED 2026-10-08 [R-IV.781(c)].** Not the traded strike's own
  IV. Under skew an OTM strike's IV is elevated, so using it is circular: the more
  expensive the tail protection, the more "reachable" X4 would judge the strike,
  and the rule would loosen exactly where it should bind. X4 asks whether **the
  underlying** can plausibly travel to break-even; the market's answer is the ATM
  term structure. The agent names the strike it read ATM from.
  **X4 tests the bucket, it does not choose it** (§ Buckets, TA-044): a FAIL on a
  non-TAIL ticket is recorded as a FAIL, never resolved by retagging to TAIL.

- **Z2 returns one of THREE results, not two:** PASS, FAIL, or **NOT EVALUABLE**.
  NOT EVALUABLE is returned for any row whose justifying timeframe the hub cannot
  read — today, every intraday row. It is not a FAIL and not a pass. The next-
  session's-close clock applies regardless. [§ Z2 trend gate]
- **X10 — flow confirms, it does not originate.** On B1 and B2 trades, an options-flow read may only *confirm* a thesis that already stands on trend and structure. A trade whose entire reason is "there was flow" is Rule 16 — short-term information flow mistaken for an edge — and does not pass.

Agents that do not recommend trades (PYTHIA, PYTHAGORAS, THALES) do not need to enforce the trade-sizing rules — but their structural / trend / macro reads may inform whether a trade meets these gates when other agents evaluate.

---

## § Asset-Class Routing Framework

Each agent routes to an asset-class-specific reference playbook (typically `references/equities.md` and `references/crypto.md`).

Universal routing rule: **Don't blend playbooks.** If the instrument spans both (e.g., a crypto-adjacent equity like COIN, MSTR, MARA), use the equities playbook — the trade is in stock/options form, even if the underlying exposure is crypto.

Each agent's `SKILL.md` retains its specific routing configuration (default profile periods, sub-asset-class branching, instrument-specific defaults). The blend-prevention rule above is universal; the configuration specifics are agent-specific.

## § Crypto Data Discipline

Applies to every agent that reads `hub_get_crypto_state` (funding / open_interest / basis / liquidations / regime / tape_health / session). These are capability/operational rules, not methodology — the derivative-signal *interpretation* lives in `docs/the-stable/` (cited per agent in each `references/crypto.md`).

1. **Hourly vintage.** `funding`, `open_interest`, `basis`, and `liquidations` are read from the cycle engine's hourly snapshot (`crypto_cycle_log`), not a live fetch. Use them for positioning and regime context, **not** for intraday timing or B3 scalp triggers. Liquidations especially: an hourly snapshot can miss a cascade that fired and resolved between samples.
2. **Never call `hub_get_quote` bare** for BTC, ETH, SOL, HYPE, ZEC, or FARTCOIN — it returns an equity/ETF collision. Use `hub_get_crypto_quote` (or `hub_get_quote(..., asset_class="EQUITY")` only if you specifically mean the colliding stock).
3. **No inferred scores.** `regime` and `cta_zone` are labeled engine classifications, not numbers. Never convert them to a score, and never infer the −45..+35 Market Structure Filter value — it is deliberately not exposed.
4. **FARTCOIN coverage gap.** FARTCOIN's cycle block lags materially behind its `regime` and `tape_health` blocks. Expect per-block divergence on that symbol; it is correctly reported, not a bug — and per the multi-block rule above, penalize only the block you used, never the top-level rollup.
