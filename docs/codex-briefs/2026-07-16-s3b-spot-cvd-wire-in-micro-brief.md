# CC MICRO-BRIEF — S-3b: Spot-CVD Wire-In (completes R-2 Done-11)

**Target: tomorrow's first deploy — strictly AFTER tonight's S-3 overnight live checks (autonomous hourly-job fire + hot-reload proof) clear against the current container.**
Drafted 2026-07-16 evening, folded into the Post-R-2 checkpoint ruling (`post-r2-checkpoint-2026-07-16.md`).
**GATE: Do not execute tonight. Do not deploy tonight — this is a same-night AUTHOR-ONLY item per Nick's explicit sequencing.**

## Why this exists

S-3's completion report (`5bb61e0`) hit the §5.1 hard-stop: no live SPOT trade feed exists on Railway for any symbol (Binance spot geo-blocked in this context, no OKX spot feed wired), so `crypto_tape_health_engine.py` ships correctly honest — `NA:SPOT_FEED_UNAVAILABLE` for all six symbols — but Done-11's "one shadow CVD event fired end-to-end" sub-requirement is structurally unmet. The checkpoint ruling: **approved as its own micro-brief (not S-4/S-5 scope)** — OKX spot trades is the same already-sanctioned vendor (perp/swap already flows from OKX per S-1's geo-block decision), so this activates already-shipped machinery with zero new vendor and $0 spend.

## Preconditions

- `git fetch && git status` — confirm local matches `origin/main` at `5bb61e0` or a verified descendant. Report exact state before any edit.
- Pathspec-only commits, message via `C:\temp\commitmsg.txt`.
- **Do not touch `bias_scheduler.py` without first re-running `scripts/crypto_dual_write_diff_report.py`** (standing bypass-retirement tracker instruction) — S-3b's tape-health job doesn't obviously need to touch that file, but if scope grows to include the tape-health job's own scheduling, check first.
- **Verify before building, don't assume:** `get_market_structure_context(ticker, ...)` in `backend/strategies/btc_market_structure.py:340` already accepts a `ticker` param (not BTC-hardcoded, unlike the four FA-7 clients) and computes POC/VAH/VAL via `integrations.binance_futures.get_klines(ticker, "1h", limit=24)` — a **different** code path from the sanctioned F-2 per-symbol routing (`jobs/crypto_bars.py`) and from the CVD gate's own `/api/crypto/market` → OKX-fallback path. Confirm live from Railway, per-symbol, before writing any event-anchoring logic against it: does `integrations.binance_futures.get_klines()` actually return data for all six symbols today, or does it silently fail/return empty for anything beyond BTC (it has never been audited for multi-symbol use — unlike the four FA-7 clients, no one has confirmed or denied this)? If it's BTC-only or geo-blocked with no fallback, that's a second hard-stop-class finding — flag it the same way §5.1 was flagged, do not improvise a fix inline.

## Item 1 — Wire in OKX spot CVD (small, exact-anchor)

File: `backend/bias_filters/crypto_tape_health_engine.py`

`_OKX_SPOT_INSTID` already exists in `backend/bias_filters/binance_client.py` (shipped in the FA-7 parametrization pass, `d0ed66e`) — reuse it verbatim, do not build a second mapping.

Add a new function mirroring `_fetch_perp_cvd()` (lines 98-129) exactly, but sourcing spot trades instead of swap trades:

```python
async def _fetch_spot_cvd(symbol: str) -> tuple[Optional[float], Optional[str]]:
    """Fetch spot CVD from the OKX spot trades endpoint."""
    import httpx
    from bias_filters.binance_client import _OKX_SPOT_INSTID

    instid = _OKX_SPOT_INSTID.get(symbol)
    if not instid:
        return None, None

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                "https://www.okx.com/api/v5/market/trades",
                params={"instId": instid, "limit": "50"},
            )
            data = resp.json()
            if data.get("code") != "0" or not data.get("data"):
                return None, None
            trades = data["data"]
            cvd_usd = 0.0
            for t in trades:
                try:
                    px = float(t.get("px", 0))
                    sz = float(t.get("sz", 0))
                    side = str(t.get("side", "")).lower()
                    sign = 1 if side == "buy" else -1
                    cvd_usd += sign * px * sz
                except (ValueError, TypeError):
                    continue
            return cvd_usd, "okx_spot"
    except Exception:
        return None, None
```

In `compute_tape_health()` (lines 60-95), FIND:
```python
    # --- Spot CVD: NOT AVAILABLE (§5.1 hard-stop condition) ---
    # OKX spot trades endpoint exists but is not currently wired.
    # When wired, replace this stub with the actual fetch.
    spot_cvd = None
```
REPLACE:
```python
    # --- Spot CVD: OKX spot trades (S-3b wire-in) ---
    spot_cvd = None
    spot_source = None
    try:
        spot_cvd, spot_source = await _fetch_spot_cvd(symbol)
    except Exception as exc:
        logger.debug("Spot CVD fetch failed for %s: %s", symbol, exc)
```
The existing `if spot_cvd is None:` branch (line 86) and the `_classify_and_persist()` call (line 95) need **no change** — they already handle both outcomes correctly; this is exactly the "activates without structural change" property the checkpoint ruling described. Confirm `_classify_and_persist()`'s `source` field construction still reads correctly once `spot_source="okx_spot"` is live (currently hardcodes `"okx_spot+okx_swap"` at line 167 — fine as-is, but verify against what actually got fetched rather than assuming both legs succeeded).

**Symbol coverage note:** confirm `_OKX_SPOT_INSTID` covers all six symbols before assuming full coverage — if any symbol is missing from that dict (matching the FA-7 pattern of some symbols being OKX-only or NA), tape-health for that symbol stays honestly `NA:SPOT_FEED_UNAVAILABLE`, not a silent full-coverage claim.

## Item 2 — CVD event detection (§5.3/§5.4, the larger piece — Done-11's actual "one shadow CVD event" requirement)

Wiring the feed alone produces a live tape-health STATE (SPOT_LED/PERP_LED/MIXED) — it does not by itself produce a signal-feed EVENT. Done-11 specifically requires "one shadow CVD event fired through the real deployed `process_signal_unified()`." This is new code, not a stub activation:

- **Anchor points:** POC/VAH/VAL only, per §5.3 — no free-floating "CVD moved a lot" events. Pull from `btc_market_structure.compute_volume_profile()`'s existing output (once the precondition check above confirms it's live per-symbol).
- **Event types:** `CVD_DIVERGENCE` (price makes a new local high/low near a structural level while CVD diverges) and `CVD_ABSORPTION` (large opposing CVD flow absorbed at a level without a corresponding price move) — thresholds config-driven in `crypto_cycle_config` (reuse the existing table/loader, do not create a fourth config table).
- **Persistence path:** `process_signal_unified()` ONLY — the L0 side-door question was settled law post-F-4 (S-1); `signal_type` values `CVD_DIVERGENCE`/`CVD_ABSORPTION`, `asset_class=CRYPTO`, canonical ticker (already normalized at ingress per S-3 Phase 1 — `normalize_crypto_ticker()`).
- **FA-2 (ATLAS, inherited from S-3):** every event signal must carry the full BAR_WALK-resolvable field set (canonical ticker, direction, reference price, config-driven expiry — default 24h per the S-3 brief's own default) so the S-1 F-2 outcome machinery grades it automatically. This is also how the row correctly accrues an S-2 `crypto_gate_shadow` row (expected, desirable, per S-3's completion report deviation #3 — the S-2 apparatus is intact and untouched).
- **Dedup/cooldown (§5.7):** per-symbol, per-event-type, per-level cooldown window, config-driven, using a `signals` table lookback query — no new dedup table, matching the brief's own instruction.
- **Connector re-toggle:** the checkpoint ruling states this activation does NOT trigger a connector re-toggle ("no new MCP tool — endpoint-layer only") — **unless this item's own Phase 0 finds otherwise.** If event detection ends up needing a new hub MCP surface (unlikely, but check), flag it and apply the standing Olympus-impact rule.

## Done Definition (S-3b)

1. Precondition check recorded: `get_market_structure_context`/`integrations.binance_futures.get_klines()` confirmed live per-symbol from Railway (or a second hard-stop flagged, not improvised around).
2. `_fetch_spot_cvd()` live; `compute_tape_health()` returns real `SPOT_LED`/`PERP_LED`/`MIXED` states for symbols with `_OKX_SPOT_INSTID` coverage; symbols without it stay honestly `NA:SPOT_FEED_UNAVAILABLE`.
3. One shadow CVD event (`CVD_DIVERGENCE` or `CVD_ABSORPTION`) fired through the real deployed `process_signal_unified()`, carrying the full FA-2 BAR_WALK field set, and observed both in `signals` (shadow-tagged, `asset_class=CRYPTO`) and its corresponding `crypto_gate_shadow` row (S-2 apparatus confirmed intact).
4. Cooldown/dedup proven (a second synthetic trigger within the window does not double-fire).
5. Zero live impact re-confirmed: `gating_enabled` unchanged, no new dismissals attributable to this change.
6. 4-step deployment verification per PROJECT_RULES.
7. Known-red baseline unchanged (18 FAILED, byte-identical); new tests added and green.
8. Completion report + ACK.

## Sequencing (per Nick's instruction and the checkpoint ruling)

Tonight: this brief only, committed, batched into tonight's single push with everything else. **No code written tonight, no deploy tonight.** Tomorrow: re-run S-3's overnight live-check evidence (autonomous hourly job fire, hot-reload proof) FIRST against the currently-running container; only after that evidence is clean does S-3b become the first deploy of the day.
