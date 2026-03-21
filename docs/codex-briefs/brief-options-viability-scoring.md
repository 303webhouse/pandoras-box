# Brief — Options Viability Scoring Layer (Score v2 Enhancement)

**Priority:** HIGH — the missing piece that turns chart signals into options trade assessments
**Touches:** `backend/scoring/score_v2.py`
**Estimated time:** 1–1.5 hours (single file, additive logic)

---

## Problem Statement

The scoring system evaluates whether a signal is a valid *chart pattern*. It does NOT evaluate whether that chart pattern translates into a good *options swing trade for Nick's account.* A signal with a valid 1.5 R:R setup on a $13 stock (LYFT) scores the same as a 2.3 R:R setup on a $131 stock (PLD), even though the $13 stock is nearly untradeable with options spreads.

This brief adds an **options viability** scoring section to `score_v2.py` that penalizes signals that look good on a chart but are bad options trades, and rewards signals that are naturally well-suited for multi-day options holds.

---

## What the New Factors Assess (Plain English)

Each factor answers one question Nick would ask himself before opening an options trade:

1. **"Can I even build a spread on this?"** — Stocks under ~$20 have premiums so thin that the bid/ask spread eats your edge. A $0.05-wide market on each leg means you're giving up $10/contract just to get in and out. Penalty for cheap underlyings.

2. **"Is the expected move big enough to beat time decay?"** — If the signal targets a 1.5% move on a stock that normally moves 2% per day (ATR), the move might happen in hours (good for day trading, useless for swing options). The target needs to be at least 1-2 ATRs to give an options spread enough room to profit after theta eats at it overnight.

3. **"Is the R:R good enough for options?"** — A 1.5:1 reward-to-risk ratio is fine for stock trades where you keep 100% of the move. For options spreads, you lose edge to bid/ask, theta, and early assignment risk. You need at least 2:1 to reliably profit after friction.

4. **"Are options liquid enough on this ticker?"** — Tickers with low average daily volume typically have wide options spreads. If the underlying trades less than 500K shares/day, the options will be illiquid and expensive to enter/exit.

5. **"Are options cheap or expensive right now?"** — IV rank tells you whether options are historically cheap (<30) or expensive (>70). This doesn't make a trade good or bad, but extreme IV in the wrong direction is a headwind: buying expensive options (high IV + debit spread) means you're overpaying for time value that will decay.

---

## Implementation

### File: `backend/scoring/score_v2.py`

Add the options viability section **after** the regime section and **before** the confluence placeholder. All data comes from `enrichment` (already populated by signal_enricher.py) and `signal_data` (the signal itself).

**Find the confluence placeholder (~line after the regime section closes):**
```python
    # --- Confluence bonus (placeholder — degraded until Phase 3 X1) ---
    confluence_score = signal_data.get("confluence_score")
    confluence_bonus = 0
    factors["confluence"] = {"value": confluence_score, "bonus": confluence_bonus, "note": "degraded until Phase 3 X1 scanner"}
```

**Add BEFORE that block:**

```python
    # ── OPTIONS VIABILITY LAYER ──────────────────────────────────────
    # Evaluates whether this chart signal makes a good options swing trade.
    # Penalizes setups that are valid chart patterns but poor options trades.
    # Only applies to equity signals (crypto skipped).

    options_bonus = 0
    options_factors = {}
    asset_class = (signal_data.get("asset_class") or "EQUITY").upper()

    if asset_class != "CRYPTO":
        entry_price = signal_data.get("entry_price") or enrichment.get("current_price")
        target_price = signal_data.get("target_1")
        stop_price = signal_data.get("stop_loss")
        rr = signal_data.get("risk_reward")
        atr = enrichment.get("atr_14")
        atr_pct = enrichment.get("atr_pct")
        avg_vol = enrichment.get("avg_volume_20d")
        iv_rank = enrichment.get("iv_rank")

        # --- Factor 1: Underlying price floor ---
        # Options on cheap stocks have thin premiums and wide bid/ask.
        # Below $20 is very hard to spread. $20-40 is marginal. $40+ is fine.
        price_penalty = 0
        if entry_price is not None:
            if entry_price < 15:
                price_penalty = -10  # Nearly impossible to build profitable spreads
            elif entry_price < 25:
                price_penalty = -7   # Very thin premiums, wide markets
            elif entry_price < 40:
                price_penalty = -3   # Marginal — workable but not ideal
            # $40+ = no penalty
        options_factors["underlying_price"] = {
            "value": entry_price,
            "bonus": price_penalty,
            "note": "<$15 untradeable, <$25 thin, <$40 marginal",
        }
        options_bonus += price_penalty

        # --- Factor 2: Target move vs ATR (move quality) ---
        # The signal's target move needs to be meaningful relative to
        # the stock's normal daily range. If target < 1 ATR, the move
        # could happen and reverse in the same day — bad for overnight holds.
        # Target >= 2 ATR = multi-day swing with room for options to profit.
        move_bonus = 0
        target_in_atr = None
        if entry_price and target_price and atr and atr > 0:
            target_move = abs(float(target_price) - float(entry_price))
            target_in_atr = round(target_move / atr, 2)
            if target_in_atr >= 3.0:
                move_bonus = 5    # Big multi-day swing — ideal for options
            elif target_in_atr >= 2.0:
                move_bonus = 3    # Solid swing range
            elif target_in_atr >= 1.5:
                move_bonus = 0    # Acceptable
            elif target_in_atr >= 1.0:
                move_bonus = -3   # Borderline — might not overcome theta
            else:
                move_bonus = -7   # Intraday-sized move — theta will eat this
        options_factors["target_move_atr"] = {
            "value": target_in_atr,
            "bonus": move_bonus,
            "note": "<1 ATR = intraday move, >=2 ATR = swing-worthy",
        }
        options_bonus += move_bonus

        # --- Factor 3: R:R minimum for options ---
        # Stock traders can profit at 1.5:1 R:R.
        # Options traders need higher R:R because spreads have friction:
        # bid/ask slippage, theta decay, early assignment risk.
        # 2.0+ is the practical minimum for debit spreads.
        rr_bonus = 0
        if rr is not None:
            rr_val = float(rr)
            if rr_val >= 3.0:
                rr_bonus = 5     # Excellent options R:R
            elif rr_val >= 2.5:
                rr_bonus = 3     # Good
            elif rr_val >= 2.0:
                rr_bonus = 0     # Minimum acceptable
            elif rr_val >= 1.5:
                rr_bonus = -5    # Below options threshold — stock-only trade
            else:
                rr_bonus = -8    # Poor R:R even for stocks
        options_factors["risk_reward"] = {
            "value": rr,
            "bonus": rr_bonus,
            "note": "<2.0 = stock-only R:R, >=2.5 = good for options",
        }
        options_bonus += rr_bonus

        # --- Factor 4: Options liquidity proxy ---
        # Low underlying volume = wide options bid/ask = expensive to trade.
        # This is a proxy — true options liquidity requires options-specific data
        # (which Polygon Stocks Starter doesn't provide).
        liquidity_bonus = 0
        if avg_vol is not None:
            if avg_vol >= 5_000_000:
                liquidity_bonus = 3   # Very liquid — tight options markets
            elif avg_vol >= 2_000_000:
                liquidity_bonus = 1   # Liquid enough
            elif avg_vol >= 500_000:
                liquidity_bonus = 0   # Acceptable
            elif avg_vol >= 100_000:
                liquidity_bonus = -5  # Thin — options will have wide spreads
            else:
                liquidity_bonus = -8  # Illiquid — avoid options entirely
        options_factors["liquidity"] = {
            "value": avg_vol,
            "bonus": liquidity_bonus,
            "note": "<500K avg vol = wide options spreads",
        }
        options_bonus += liquidity_bonus

        # --- Factor 5: IV rank context ---
        # High IV = expensive options. For DEBIT spreads (buying), high IV is a headwind.
        # For CREDIT spreads (selling), high IV is a tailwind.
        # Since Nick primarily trades debit spreads, penalize extreme high IV
        # and reward low-to-moderate IV (cheaper entry).
        iv_bonus = 0
        if iv_rank is not None:
            if iv_rank <= 20:
                iv_bonus = 3     # Cheap options — good for debit spreads
            elif iv_rank <= 40:
                iv_bonus = 1     # Below average — favorable
            elif iv_rank <= 60:
                iv_bonus = 0     # Normal
            elif iv_rank <= 80:
                iv_bonus = -2    # Expensive — theta drag is higher
            else:
                iv_bonus = -5    # Very expensive — debit spreads overpaying for time value
        options_factors["iv_rank"] = {
            "value": iv_rank,
            "bonus": iv_bonus,
            "note": ">80 = expensive for debit spreads, <20 = cheap entry",
        }
        options_bonus += iv_bonus

    factors["options_viability"] = {
        "total_bonus": options_bonus,
        "components": options_factors,
    }

    post_enrichment_bonus += options_bonus
```

---

## Impact Analysis (Using Friday's Signals)

Here's how each Friday signal would score with options viability added:

### LYFT sell_the_rip SHORT — flash 60, current v2 54
| Factor | Value | Bonus | Why |
|--------|-------|-------|-----|
| Underlying price | $13.12 | **-10** | Under $15 — can't build spreads |
| Target move/ATR | ~0.8 ATR (est) | **-7** | Intraday-sized move |
| R:R | 1.5 | **-5** | Below options threshold |
| Liquidity | ~15M vol | **+3** | Very liquid underlying |
| IV rank | ~45 (est) | **0** | Normal |
| **Options total** | | **-19** | |
| **New v2** | | **~35** | Drops from 54 → 35. Would not surface. Correct. |

### PLD CTA Scanner SHORT — flash 54, current v2 54
| Factor | Value | Bonus | Why |
|--------|-------|-------|-----|
| Underlying price | $131.09 | **0** | Fine for spreads |
| Target move/ATR | ~2.3 ATR | **+3** | Solid multi-day swing |
| R:R | 2.3 | **+3** | Good options R:R |
| Liquidity | ~3M vol | **+1** | Liquid enough |
| IV rank | ~35 (est) | **+1** | Below average — favorable |
| **Options total** | | **+8** | |
| **New v2** | | **~62** | Climbs from 54 → 62. Almost at threshold. Correct — this IS a viable options trade. |

### VLO Artemis LONG — already routed to INTRADAY_SETUP
Not scored for Insights. Double-filtered: regime penalty (-10) AND Artemis equity routing. Correct.

**The system now does what the committee asked for:** LYFT (bad options trade on a $13 stock) gets crushed. PLD (viable options trade on a $131 stock with 2.3 R:R) gets boosted. The scoring finally reflects options reality.

---

## Scoring Budget Summary

After this change, score_v2 factors stack as follows:

| Factor | Range | Source |
|--------|-------|--------|
| Flash score (base) | 0–100 | trade_ideas_scorer.py |
| RVOL | -3 to +5 | enrichment |
| Risk in ATR | -5 to +5 | enrichment |
| Regime alignment | -20 to +5 | bias_at_signal |
| **Underlying price** | **-10 to 0** | **enrichment (NEW)** |
| **Target move/ATR** | **-7 to +5** | **signal + enrichment (NEW)** |
| **Options R:R** | **-8 to +5** | **signal (NEW)** |
| **Liquidity** | **-8 to +3** | **enrichment (NEW)** |
| **IV rank** | **-5 to +3** | **enrichment (NEW)** |
| Confluence | 0 (placeholder) | future |
| **Max penalty** | **-38** | |
| **Max bonus** | **+16** | |

A signal with flash score 65 that's a terrible options trade (cheap stock, low R:R, no move, illiquid) would drop to ~27. A signal with flash score 65 that's a perfect options trade would climb to ~81. That's the right spread — it means the options layer has real teeth.

---

## What Nick Sees

Nothing changes in the UI. The v2 score just becomes more accurate. Signals that are bad options trades will score lower and either fall below the threshold or rank lower in the Insights panel. Signals that are good options trades will score higher and rise to the top.

The `score_v2_factors` JSON (visible in signal detail view) will now include an `options_viability` section with each component's value and bonus, so Nick (or the committee) can see exactly why a signal scored the way it did.

---

## Edge Cases

1. **Crypto signals skip entirely.** The `asset_class != "CRYPTO"` guard ensures crypto signals (which trade perpetual swaps, not options) are unaffected.

2. **Missing enrichment data.** If `entry_price`, `atr`, `avg_volume`, or `iv_rank` are null, the corresponding factor contributes 0 bonus (not penalized for missing data). This matches the existing pattern for RVOL and risk_in_atr.

3. **Stocks Nick trades as equity (Fidelity Roth).** These signals would get penalized for low R:R or cheap underlying even though they're equity trades. This is acceptable because the Insights panel is for OPTIONS trade ideas. If Nick wants stock-only ideas, the raw `/trade-ideas` endpoint still shows everything unfiltered.

4. **Credit spreads and IV.** The IV penalty assumes debit spreads (Nick's primary structure). If Nick starts trading credit spreads regularly, the IV scoring should flip: high IV = bonus for credit spreads. That's a future toggle, not built now.

---

## Build Order

| Step | File | What |
|------|------|------|
| 1 | `scoring/score_v2.py` | Add options viability section (5 factors) before confluence placeholder |

That's it. Single file, additive logic, no other files touched.

---

## Verification Checklist

- [ ] Signal on a <$15 stock gets `options_viability.components.underlying_price.bonus: -10`
- [ ] Signal on a >$40 stock gets `options_viability.components.underlying_price.bonus: 0`
- [ ] Signal with R:R 1.5 gets `options_viability.components.risk_reward.bonus: -5`
- [ ] Signal with R:R 2.5 gets `options_viability.components.risk_reward.bonus: +3`
- [ ] Signal with target < 1 ATR gets `options_viability.components.target_move_atr.bonus: -7`
- [ ] Signal with target > 2 ATR gets `options_viability.components.target_move_atr.bonus: +3`
- [ ] Crypto signals have no `options_viability` penalties
- [ ] `score_v2_factors` JSON includes the full `options_viability` breakdown
- [ ] Overall v2 score shifts meaningfully: cheap-stock/low-RR signals drop 15-30 points

---

## Commit

```
feat: options viability scoring layer — underlying price, move size, R:R, liquidity, IV
```
