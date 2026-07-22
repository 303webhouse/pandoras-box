# DEF-CRYPTO-VP-ANCHOR — Phase 0 Findings

**Authored:** 2026-07-22 (Claude Code, verification lane)
**Brief:** `docs/codex-briefs/2026-07-22-def-crypto-vp-anchor-brief.md`
**Status:** Phase 0 complete (stop-gate cleared). Rulings received and recorded below. No code changed in Phase 0.
**Severity:** P0 — fake-healthy. `vp_status: "ok"` served on confidently-wrong structural levels.

---

## 1. Root cause (CONFIRMED, adversarially verified)

The volume-profile leg selects its window with a **positional tail slice** over a bar list that is **never sorted after fetch**:

```python
# backend/hub_mcp/tools/crypto_market_profile.py:58,62
bars_1h = await fetch_crypto_ohlc(base_symbol, use_daily=False)   # 15m bars, vendor order
recent_24h = bars_1h[-24:]                                        # POSITIONAL slice
```

`fetch_crypto_ohlc` → `_fetch_full_ohlc` (`backend/jobs/crypto_bars.py:140-164`) dispatches to UW / Binance / OKX fetchers that append bars **in vendor-returned order**. There is **no `sort`/`sorted`/`reverse`** anywhere in that path (grep-confirmed). The fetch pulls up to **500 bars (UW/Binance, ~5.2 days) or 300 (OKX, ~3.1 days)** at 15m.

- If the vendor returns **ascending** (oldest-first, e.g. Binance) → `[-24:]` = newest 24 → **correct 6h window**.
- If the vendor returns **descending** (newest-first, e.g. UW, OKX) → `[-24:]` = the **oldest 24 bars** of the fetch → a 6h slice **3–5 days stale**, anchored to old (lower or higher) prices.

**Why the session leg is correct and the VP leg is not — same list, different selector:**

```python
# :114 — session leg selects by TIMESTAMP filter (order-independent → correct)
session_bars = [b for b in (bars_1h or []) if b[0] >= partition_start]
```

The session leg reads the *same* `bars_1h` and returns the correct `session_low` (matches `hub_get_crypto_quote.low_24h` exactly). So the current bars **are** present in the list; only the positional VP selector lands on the stale block.

**Arithmetic entailment (decisive — does not depend on knowing UW's order):** `compute_volume_profile` sets `price_min = min(lows)`, `price_max = max(highs)` of the *passed* klines, and POC is always a bin inside `[price_min, price_max]` (`btc_market_structure.py:52-87`). A POC below the true 24h low is **mathematically impossible** unless the fed bars are a different, older window. Since the session leg proves current bars exist in the list, the positional slice must be selecting elsewhere → the list is non-ascending. The mechanism is *entailed by the observation*, not assumed.

---

## 2. The three-vendor natural experiment (live evidence, 2026-07-22 ~13:55 UTC)

All six tracked symbols were pulled live via `hub_get_crypto_market_profile`. Guard column = `VAH < session_low OR VAL > session_high`.

| Symbol | Vendor | POC | VA (VAL–VAH) | Session L/H | POC vs session | VA width | Guard |
|--------|--------|-----|--------------|-------------|----------------|---------|-------|
| BTC | UW | 63,039.61 | 62,758.83–63,150.23 | 65,484 / 66,114 | **−3.7% below** | 0.62% | 🔴 FIRE (VAH<SL) |
| ETH | UW | 1,835.31 | 1,824.36–1,838.97 | 1,911.56 / 1,941.60 | **−4.0% below** | 0.80% | 🔴 FIRE (VAH<SL) |
| SOL | UW | 74.70 | 74.32–74.81 | 76.93 / 77.90 | **−2.9% below** | 0.66% | 🔴 FIRE (VAH<SL) |
| HYPE | OKX | 60.91 | 60.77–61.13 | 58.09 / 59.22 | **+2.9% above** | 0.59% | 🔴 FIRE (VAL>SH) |
| FARTCOIN | OKX | ~0.13* | ~0.13–0.13* | 0.1343 / 0.1388 | below* | ~0%* | 🔴 FIRE (VAH<SL) |
| **ZEC** | **Binance** | **515.99** | **513.34–517.27** | **511.37 / 521.21** | **IN RANGE** | 0.76% | 🟢 clears |

*\* FARTCOIN's ~$0.13 price collapses under `round(x, 2)` — see §7 (separate precision defect, not fixed here).*

**This is proof, not inference.** The one symbol whose value area sits correctly inside its session range — **ZEC** — is the one symbol sourced from **Binance**, whose `/klines` returns **ascending**, so `[-24:]` grabs the freshest 24 bars. Both **UW** symbols and both **OKX** symbols (which return **newest-first**) are displaced. **HYPE's upward displacement** (VA *above* the session range, because HYPE fell over the stale gap) confirms the failure is **bidirectional**, and confirms the guard's `VAL > session_high` clause is load-bearing.

**Vendor return-order (confirmed empirically by the experiment):** UW descending, OKX descending, Binance ascending.

**Blast surface: 5 of 6 symbols** serve wrong levels under `vp_status: "ok"`. Only ZEC (Binance) is correct — and even ZEC is only a 6h window (the "too narrow / mislabeled" part; see §5).

---

## 3. Equity path — NOT shared (scope does NOT extend)

`hub_get_market_profile` (`backend/hub_mcp/tools/market_profile.py`) → `services/read_only/market_profile.py` reads **pre-computed Pine levels** from the `pythia_events` Postgres table via `SELECT ... ORDER BY timestamp DESC LIMIT 1` (`:91-102`). **No bar fetch, no positional slice.** Neither condition of the crypto defect is present. The 2026-07-02→15 PYTHIA stale-MP incident was a *staleness* class (row predates session → `stale`), a categorically different defect. **The fix stays confined to the crypto path.**

---

## 4. Blast radius — two surfaces, and it SCORES (Ruling #3 answer)

**Surface A — the MCP tool (`hub_get_crypto_market_profile`):** computes on-the-fly, **never persisted**. Ephemeral per-call.

**Surface B — the scoring module (`get_market_structure_context`, `btc_market_structure.py:340-458`):** identical `[-24:]` slice (mirrors the tool "byte-for-byte" per its own comment, `:358-369`). Its `poc/vah/val` **are persisted** to `signals.enrichment_data → 'market_structure'` via `persist_enrichment`, **since 2026-07-19 14:50:48Z** (first surviving row post-DEF-ENRICH-CLOBBER, `34143ee`).

**Does `market_structure` feed the score, or is it enrichment-only? It SCORES — selectively, by producer path:**

| Producer | Path | Modifier → `score`? | Score-contaminated? | Persisted VP contaminated? |
|----------|------|--------------------|--------------------|---------------------------|
| Session_Sweep / Liquidation_Flush / Funding_Rate_Fade | `crypto_setups.py:532` `sig["score"] += score_modifier` | **YES** | **YES** → flash → `score_v2` → `COALESCE(score_v2,score)` | YES |
| TradingView-webhook crypto | `tradingview.py` `_process_with_market_structure` | NO (`_market_structure_modifier` set at `:156`, **zero downstream readers**) | NO | YES (enrichment-only) |
| **CVD_ABSORPTION** | `crypto_tape_health_engine.py` → `process_signal_unified` directly (`:441`, fixed `score: 50`) | N/A (never calls market structure) | **NO** | NO |

Key consequences:

- **`compute_score_v2` does not read `enrichment['market_structure']`** — `score_v2 = flash + post_enrichment_bonus` where the bonus is rvol/risk/regime/options/darkpool only. So the *only* way the VP reaches the score is via the flash-score mutation at `crypto_setups.py:532`.
- **CVD_ABSORPTION is clean** both ways (fixed base score, no MS enrichment). The prior **"~half of CVD_ABSORPTION below floor"** prediction is **not** invalidated.
- **The `CRYPTO_ALERT_MIN_SCORE=28` floor calibration (n=55) is *partially* contaminated:** CVD_ABSORPTION (n=33) clean; the other live `crypto_setups` strategy (~n=22) carries the VP defect. The VP component is stuck at **−5** ("outside value area, extended") for all 5 displaced symbols in both directions (entry always outside the phantom VA), a downward bias of ~0–15 pts (−5 replacing a legitimate −10..+10).
- **Score-contamination birthdate ≠ persistence birthdate.** Scoring happens at signal creation regardless of whether enrichment survives; the score-contamination traces to the **S-3b F-2-bar reroute** (`btc_market_structure.py:358-369`), likely *earlier* than 2026-07-19. The remediation brief needs both timelines.

---

## 5. Window contract: docs wrong, backlog incomplete

- **Docs** (tool DESCRIPTION `:37`; `btc_market_structure.py` comment): "last 24 hours of 1H klines" — **wrong on both axes.**
- **Reality:** 24 × 15m = **~6h** of coverage, from wherever the positional tail lands.
- **Backlog item (a)** ("6h × 15m actual vs 24h × 1H documented") was **right on granularity but incomplete** — it flagged *narrow* (labeling), missed *stale* (data). Per Ruling, reclassified P3-doc → P0-data.

Per **Ruling #1**, the ordering fix and the window-length change are **separated**: fix the `[-24:]` ordering now; correct the docs to say **6h × 15m** (matching reality); the 6h-vs-24h methodology decision is ratified separately by Nick + PYTHIA.

---

## 6. Guard — validated on live data

The brief's floor invariant — **flag if `VAH < session_low` OR `VAL > session_high`**, cross-referencing the *independent* timestamp-filtered session leg — **fires on all 5 defective symbols and clears ZEC** (see §2 table), proven bidirectional. Per **Ruling #4**, pair it with a direct **freshness assertion** (`recent[-1][0] >= now − ~20min`) after sorting: symptom-detector (VAH/VAL) plus cause-detector (freshness). On violation, return `degraded`/`unavailable` with a stated reason — never serve the values.

Post-fix width sanity (Ruling / brief Phase 2): on the same 6h window with *current* bars, VA width should exceed today's ~0.6–0.8%. If it doesn't move, the sort didn't take.

---

## 7. Corrections to the brief (reported per "if Phase 0 contradicts the brief, stop and report")

1. **5 of 6 symbols defective, not 2.** BTC/ETH confirmed in the brief; SOL (UW) and HYPE/FARTCOIN (OKX) added; ZEC (Binance) is the sole clean one.
2. **Surface B (persisted `enrichment_data` + scoring) was missed entirely** by the brief, which scoped only the MCP tool.
3. **Backlog location:** the brief (`:54`) says `docs/build-backlog.md`; the item actually lives at **`docs/workstreams.md:82` item (a)**. `build-backlog.md` exists but does not contain it.
4. **Separate precision defect (log only, do not fix here):** `compute_volume_profile` does `round(x, 2)`, collapsing sub-dollar assets (FARTCOIN ~$0.13). Logged for a future pass.

---

## 8. Rulings recorded (2026-07-22)

1. **Separate ordering fix from window change.** Fix `[-24:]` ordering (timestamp filter + sort). Do NOT reconcile 6h→24h in the same pass. Correct docs to 6h × 15m. Window length ratified separately (Nick + PYTHIA).
2. **Surface B split by risk class:** IN SCOPE NOW — the `[-24:]` fix in `btc_market_structure.py`, same commit (don't leave the twin live). SEPARATE BRIEF — remediation of persisted `enrichment_data` rows since 2026-07-19 (destructive prod write; pre-image + `--i-have-go` + predicate + ATLAS, DEF-ENRICH-CLOBBER ceremony).
3. **market_structure SCORES** (this doc §4) — selectively via `crypto_setups.py`; CVD_ABSORPTION clean; floor partially affected. Blast radius materially larger for the separate brief.
4. **Sequencing:** (c) commit this findings doc + annotate `workstreams.md:82`, then (a) ship guard + ordering fix TOGETHER (VAH/VAL check + freshness assertion). ATLAS gates the persisted-row remediation, NOT the read-path fix — "a fail-closed guard plus a sort cannot make things worse."
5. **FARTCOIN `round(x,2)`** — separate, logged (§7), not fixed here.
