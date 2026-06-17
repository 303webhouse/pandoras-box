# Brief: Port THALES + DAEDALUS into VPS Committee (pivot2_committee.py)

**Date:** 2026-04-22
**Priority:** P1 (closes the gap between Olympus as designed vs Olympus as deployed)
**Target:** Claude Code (VSCode) — with Titans design review for prompt architecture
**Estimated effort:** 2-3 hours (prompt drafting + wiring + verification)
**Origin:** The Olympus committee that runs on the VPS (`pivot2_committee.py`) currently has 4 agents: TORO, URSA, TECHNICALS (really PYTHAGORAS), PIVOT. The design Olympus in conversation has 6 agents: TORO, URSA, PYTHAGORAS, PYTHIA, **THALES**, **DAEDALUS**, PIVOT. Missing from production: THALES (sector specialist) and DAEDALUS (options/derivatives specialist). 2026-04-22 MO review confirmed the gap — URSA caught the earnings/FOMC timing cluster, but a proper DAEDALUS would have killed the options side of the thesis immediately on IV-crush-into-earnings analysis.

---

## Prerequisite

**This brief depends on `2026-04-22_committee-context-builder.md` being completed first.** THALES and DAEDALUS are useless without the per-ticker data hydration they'd reason over. Sequencing: context builder ships → this brief ships next.

---

## THALES — Sector / macro specialist

### Role definition

Sector-level reasoning that the other agents don't cover:
- Business model nuances (e.g., utilities vs consumer staples vs semiconductors have different regime behaviors)
- Competitive dynamics within sector (is the signal's ticker a leader, laggard, or rotator?)
- Sector momentum / rotation (is money flowing IN or OUT of this sector this week?)
- Macro headwinds / tailwinds that technicals miss (tariff changes, regulatory shifts, commodity prices)
- Higher-beta alternatives in same sector (if TORO wants MO long, why not VZ or KO instead?)

### Data THALES needs (hydrated by context builder)

- Signal ticker's sector + industry
- Sector ETF relative performance (XLU for utilities, XLK for tech, etc.) — compare to SPY
- Peer tickers in same sub-industry and their recent moves
- Macro context already present: bias composite, DEFCON, commodity moves

### THALES prompt skeleton

```python
THALES_PROMPT = """
You are THALES, the sector and macro specialist on the Olympus committee.

Your mandate:
- Evaluate whether the signal's ticker is a rational expression of the current macro / sector regime
- Flag sector rotations that contradict the signal direction
- Identify higher-beta or cleaner alternatives within the same sector if the thesis is directionally right but the ticker is wrong
- Surface macro or regulatory headwinds that chart-based agents would miss

Do NOT:
- Fabricate sector data you weren't given
- Restate TORO or URSA's arguments — you're the sector lens, not a generalist bull/bear

You have been given:
- Signal: {signal_description}
- Ticker sector/industry: {sector_context}
- Sector ETF relative performance (5d, 20d): {sector_relative}
- Peer comparables: {peer_context}
- Macro regime: {macro_context}

Return in this format:
## THALES Analysis
## Sector Regime Read
[one paragraph: is the sector trending, rotating, or neutral?]
## Ticker Fit
[does this specific ticker fit the sector thesis, or is there a better vehicle?]
## Macro / Sector Risks
[any headwinds the other agents may miss?]
## Conviction: LOW / MEDIUM / HIGH
"""
```

---

## DAEDALUS — Options / derivatives specialist

### Role definition

The one agent that thinks in derivatives specifically:
- IV rank + term structure (is premium cheap or expensive for THIS ticker at THIS moment?)
- IV crush timing (earnings-within-window? Fed day? other known vol events?)
- GEX / gamma walls (does dealer positioning support or fight the trade?)
- Max pain for the trade's likely expiry
- Put/call skew and ratio
- Optimal structure selection (naked call vs debit spread vs ratio — which fits the thesis)
- Flags when derivatives pricing explicitly contradicts the directional thesis

### Data DAEDALUS needs (hydrated by context builder)

- Ticker's IV rank (1y), ATM IV, realized HV
- Days to next earnings + announce time
- GEX (call_gamma, put_gamma, net)
- Option chain snapshot near target strike
- Max pain for nearest weekly + monthly expiry

### DAEDALUS prompt skeleton

```python
DAEDALUS_PROMPT = """
You are DAEDALUS, the options and derivatives specialist on the Olympus committee.

Your mandate:
- Evaluate whether the DERIVATIVES market agrees with the directional thesis
- Price optimal structure: cheap calls, spread, ratio, or "don't use options at all"
- Flag IV regime: is the premium cheap, fair, or expensive for the holding window?
- Identify IV-crush events within the trade window (earnings, Fed days, NFP)
- Read dealer positioning (GEX) for support/resistance implications
- Flag when max pain pins against the trade direction

Do NOT:
- Restate directional arguments — you're the vol/structure lens
- Recommend a specific contract unless you have full chain data

You have been given:
- Signal: {signal_description}
- IV rank (1y): {iv_rank}
- Realized HV / ATM IV: {hv} / {atm_iv}
- Next earnings: {next_earnings_date} ({days_to_earnings}d from now, {announce_time})
- GEX: call_gamma={call_gamma}, put_gamma={put_gamma}, net={net_gex}
- Max pain (nearest monthly): {max_pain}
- Option chain near target strike (if provided): {chain_snapshot}

Return in this format:
## DAEDALUS Analysis
## IV Regime
[IV rank interpretation: cheap / fair / expensive; current vs 1y percentile]
## Timing Risks
[earnings, Fed, NFP, JOLTS, etc. in the likely holding window]
## Structure Recommendation
[naked long, debit spread, ratio, or SKIP — with reasoning]
## Dealer Positioning Read
[does GEX support or fight the trade? where are the walls?]
## Conviction: LOW / MEDIUM / HIGH
"""
```

---

## Committee flow changes

### Current (pivot2_committee.py)

Two-call architecture:
1. Combined analyst call (TORO + URSA + TECHNICALS), max_tokens=2500
2. PIVOT synthesis, max_tokens=1500

### New

Decide between:
- **Option A:** 3 analyst calls (TORO+URSA, TECHNICALS+PYTHIA, THALES+DAEDALUS) + PIVOT synthesis = 4 calls
- **Option B:** One mega-analyst call with all 6 agents embedded in the prompt, max_tokens=4000 + PIVOT synthesis = 2 calls
- **Option C:** Keep 2 calls, add THALES + DAEDALUS to the combined analyst prompt alongside TORO/URSA/TECHNICALS, bump max_tokens to ~3500

**Recommendation: Option C.** Keeps call count + cost flat. Bumps per-call tokens by ~1000. Net cost impact: probably +$0.03/run. Minimal.

### Response parsing

`parse_combined_analyst_response` in `pivot2_committee.py` currently splits TORO/URSA/TECHNICALS out of a formatted response. Extend to also extract THALES and DAEDALUS sections. Update the parser with new section markers.

### PIVOT synthesis

PIVOT needs to weigh all 6 voices (currently weights 3). Update PIVOT_PROMPT to reference THALES and DAEDALUS outputs. Add conviction-weighting: DAEDALUS HIGH-bearish on IV crush should be a near-veto for options trades, independent of direction.

---

## Titans design question

Before wiring, quick Titans pass:
- **ATLAS:** Is Option C the right token economics? Would Option A (4 calls) give meaningfully better per-agent reasoning at 2x cost?
- **ATHENA:** Is any agent redundant? E.g., does PYTHAGORAS (technicals) still have a distinct role when TECHNICALS already handles charts? (The conversation-Olympus treats them as the same agent; VPS currently calls the chart agent "TECHNICALS". Unify the naming.)

---

## Verification

1. Run committee on a real signal post-deploy (e.g., once LCID unsticks and runs)
2. Discord embed should show FIVE analyst sections (TORO / URSA / PYTHAGORAS / THALES / DAEDALUS) + PIVOT synthesis, not three
3. THALES section should reference the ticker's sector and a peer comparable, not just restate macro
4. DAEDALUS section should reference IV rank, next earnings date, and structure recommendation
5. PIVOT synthesis should cite at least one THALES or DAEDALUS finding in its final call
6. Spot-check token usage — should not exceed ~28K input tokens per run (vs prior ~20K)

---

## Done when

- [ ] THALES + DAEDALUS prompts drafted and tested against 2-3 historical signals
- [ ] `pivot2_committee.py` combined analyst prompt extended, max_tokens bumped
- [ ] `parse_combined_analyst_response` extended to handle new sections
- [ ] PIVOT synthesis prompt updated to weigh 6 voices
- [ ] Live test run on a real signal shows all 5 analyst voices in Discord embed
- [ ] Token usage per run within acceptable bounds (~25-30K input)
- [ ] Documented in committee architecture notes
