# BRIEF — BIAS-FACTOR-AUDIT

**Authored:** 2026-07-23, coordination lane
**Type:** READ-ONLY investigation. No factor changes, no reweighting, no engine edits, no deploys. The only writes are the findings doc and this brief's filing.
**Origin:** Nick challenged four composite factors against the live tape on 2026-07-23 and was right on all four checks that could be externally verified. The composite has never had a per-factor audit against external reality.
**Priority inside the brief:** `credit_spreads` first — if its input is stale or mis-signed, that is a live fake-healthy defect on a surface feeding every committee pass and the kill switch.
**Titans review:** not required — read-only investigation, per the DEF-FUNDING-DUTY-CYCLE precedent. Recorded so the skip is deliberate. ATLAS enters only if a defect fix follows.

---

## TASK 0 — FILING

```
cd /d C:\trading-hub
git fetch origin && git status
git mv 2026-07-23-bias-factor-audit-brief.md docs\codex-briefs\
git add docs/codex-briefs/2026-07-23-bias-factor-audit-brief.md
git commit -F C:\temp\commitmsg.txt
git push origin main
```

---

## WHY THIS EXISTS — THE VERIFIED CONTRADICTIONS

Pulled live 2026-07-23 ~15:45–15:55Z. These anchors are fixed; verify against them, not against my prose.

| External reality (verified) | Composite factor says | Tension |
|---|---|---|
| 10Y **4.711%** (+5.4bp day; 4.541 → 4.711 over 5 sessions). 30Y **5.184** (5.064 five sessions ago). 5Y 4.467 (+19.4bp/5d). 3M 3.783. Source: `hub_get_stable_rates_fx` 15:47Z | `yield_curve` **+0.1** (bullish) | A bear steepening — long end surging — *widens* the 10Y−3M spread (0.928), so a slope-only factor scores a rate shock as healthy |
| VIX **19.87, +19.41% on the day** (Yahoo, 15:53Z) | `vix_term` **+0.2**, `iv_regime` **+0.2** | Structure/percentile readers; a 19% one-day spike carries no weight until the curve inverts |
| 2026 commentary documents material HY spread widening (~200bp over two months toward ~450bp; "widening from compressed levels," Apr 2026) | `credit_spreads` **+0.457** (strongly bullish) | Either level-anchored vs recession thresholds, stale input, or mis-signed. **Cannot be adjudicated without reading the source — that is this brief** |
| Nick: labor data unreliable ("weird things going on") | `initial_claims` **+0.5** AND `sahm_rule` **+0.5** | Both ride the same BLS data → **+1.0 combined** bullish contribution on questioned input |

Composite (daily, 15:4xZ): **−0.0165 = NEUTRAL**, 20/20 factors `is_stale: false`, `gex_regime: MOMENTUM`, no manual override.

**The weights problem, with arithmetic:** the tool returns `weight: null` for all 20 factors, yet the unweighted mean of the 20 scores is **−0.041** while the reported composite is **−0.0165**. Non-uniform weights (or normalization/clamping) exist and are not exposed. Until the aggregation is located, no one can compute what any factor adjustment does to the composite.

---

## PHASE 0 — PER-FACTOR PROTOCOL

For each factor below, produce four answers with file/line evidence:

1. **Input source + INPUT freshness.** Name the vendor/series (e.g., FRED series ID), the fetch path, the cache, and the as-of date of the data the score was computed from. *Compute-recent is not input-current* — the VP-anchor defect was precisely fresh computation on stale input, and `staleness_seconds` in the payload measures the computation. Trace to the input.
2. **Sign convention vs stated intent.** What does positive mean in the code, and does the implementation match the factor's name/intent? Quote the scoring expression.
3. **External cross-check.** Score the factor by hand from the verified anchors above (or the factor's own live input) and compare to the emitted score. Name any divergence.
4. **Level/structure vs velocity.** Does the factor consume rate-of-change at all, or only level/structure? Classify: VELOCITY-AWARE / LEVEL-ONLY / STRUCTURE-ONLY.

### Factor list, in priority order

| # | Factor | Score now | Specific questions |
|---|---|---|---|
| 1 | **credit_spreads** | +0.457 | **PRIORITY.** Which spread series? As-of date of the input? Level-vs-RoC scoring? If the input shows 2026 widening and the score is +0.46, quote the exact mapping that produces it. ⚠ HYG price is NOT a valid cross-check today — the 10Y surge moves HYG on duration with spreads flat; check the actual spread input |
| 2 | **yield_curve** | +0.1 | Confirm slope-only (10Y−3M). Confirm no factor anywhere consumes rate LEVEL or VELOCITY. This is expected to confirm the gap, not find a bug |
| 3 | **vix_term** | +0.2 | Which legs (VIX/VIX3M? futures?)? Contango/backwardation thresholds? Confirm velocity-blind |
| 4 | **iv_regime** | +0.2 | v2 percentile — window length, percentile→score mapping, convention (does high IV percentile score bullish, bearish, or premium-regime-neutral)? **Document only — its 60-day shadow validation is ongoing; do not touch** |
| 5 | **initial_claims** | +0.5 | Series + release cadence + revision handling. Where WOULD a quality discount or weight change live — config or hardcoded? |
| 6 | **sahm_rule** | +0.5 | Same questions. Note explicitly that #5 and #6 share upstream BLS data — a data-quality concern hits both |
| 7 | **copper_gold_ratio** | +0.2 | Input + window. Gold printed ~$4,06x on 7/22 (+1.2%) then GLD −2.07% on 7/23 — volatile regime; verify the input is current and the convention (ratio up = risk-on?) is implemented as intended |

### Aggregation + staleness thresholds (system-level)

8. **Locate the aggregation formula** — weights, normalization, clamping. Name file/line. Explain −0.041 mean vs −0.0165 composite. Report whether weights are config or hardcoded.
9. **Why does the tool emit `weight: null`?** Recommend (do not implement) the one-line exposure of real weights in `hub_get_bias_composite`.
10. **Per-factor staleness thresholds:** `excess_cape` at 27,939s and `savita` at 3,858,340s (~44 days) both report `is_stale: false`. Confirm the thresholds are cadence-appropriate per factor and document the threshold table. A monthly factor legitimately lives for a month; confirm that's encoded, not accidental.
11. **Bonus, low priority:** document what `gex_regime` ("MOMENTUM") is and who consumes it.

---

## STOP CONDITIONS

- **If any factor's implementation contradicts this brief's description of it, the brief is wrong, not the codebase.** Report and continue the audit with the corrected understanding — do not silently reconcile.
- **If credit_spreads turns out actively broken** (stale input or sign error): report immediately as a P1 finding with the DEF- prefix recommendation — do not fix in this brief. The fix is its own gated change because the composite feeds committee conviction and the kill switch.
- **Read-only means read-only.** No config changes, no weight edits, no factor-score adjustments, regardless of findings.

## STANDING TRAPS

- `::text`-cast any `timestamp without time zone` reads; the postgres MCP renders naive timestamps +6h **on display only**.
- Pathspec-only commits; message via `C:\temp\commitmsg.txt`.
- Suite untouched: this brief adds no tests and no code — `git diff --stat` is docs-only. Known-red reference: **17f / 1s / 200e**.

---

## DELIVERABLE

`docs/codex-briefs/bias-factor-audit-phase0-findings.md`:

1. Per-factor table: input source, input as-of, sign convention (quoted expression), hand-scored vs emitted, velocity classification.
2. The aggregation formula, weight table, and the null-weight explanation.
3. The staleness-threshold table.
4. **A recommendations queue for Nick's ratification — recommendations only, nothing executed:**
   - credit_spreads: verdict (correct-by-convention / stale-input / mis-signed) and the fix path if broken
   - claims + sahm: the concrete mechanism available for a quality discount (config weight vs code), with the arithmetic of a 50% haircut on the composite using the REAL weights
   - **FACTOR-RATE-SHOCK proposal:** a 10Y-velocity factor (the 5-session ghost in `hub_get_stable_rates_fx` already provides the input) — shadow-by-default, post-vacation build, Nick ratifies
   - vix_term velocity blindness: note only; pairs with the A-11 CONFLICTED-state display item
   - weight exposure in the hub tool: one-line follow-up change
5. `workstreams.md` row appended.

---

## OLYMPUS IMPACT

The composite is Context A for **every** committee pass and the input the kill switch caps. If credit_spreads is broken, every conviction level issued this week was computed on a corrupted factor — the finding would retroactively caveat those passes, and PIVOT should be told at the next pass. No skill or tool changes in this brief; impact is informational until a fix ships.
