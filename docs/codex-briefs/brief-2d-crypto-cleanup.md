# Brief 2D: Crypto Cleanup & Archive

## Summary

Clean up the dead standalone crypto-scalper directory, remove orphaned references, and update documentation to reflect the completed Phase 2 architecture.

## 1. Archive Standalone Crypto Scalper

The `crypto-scalper/` directory at repo root is a dead standalone app (~7,140 lines) that was never deployed. Strategy logic has been ported to `backend/strategies/crypto_setups.py` and `backend/integrations/binance_futures.py`.

### Action
Delete the entire `crypto-scalper/` directory from the repo:
```
crypto-scalper/
  backend/         # Dead FastAPI app (port 8001)
  frontend/        # Dead standalone UI
  data/            # Empty journal
  README.md        # Breakout prop account docs (info preserved in Brief 2B)
  requirements.txt
  start.bat
```

Do NOT archive to an `archive/` folder — it's in git history if we ever need it. Clean delete.

## 2. Remove Orphaned Frontend References

In `frontend/app.js`, search for and clean up:

- Any references to `localhost:8001` (the standalone scalper's port)
- Any fetch calls to the standalone scalper's API
- Comments referencing the standalone crypto-scalper app
- Dead functions that only existed to bridge to the standalone app

Also verify that the "MOVED TO CRYPTO-SCALPER" comment was removed in Brief 2A. If any survived, remove them now.

## 3. Update crypto_market.py Hardcoded BTC Lookups

GPT flagged that `backend/api/crypto_market.py` hardcodes BTC spot/perp venue lookups. Since Brief 2A added symbol propagation (frontend passes selected symbol), verify that the backend endpoint actually uses the `symbol` query param throughout, not just at the top level.

Check the internal functions:
- `get_market_snapshot()` — does it pass the symbol param to venue lookups?
- Are spot/perp symbol pairs (e.g., BTCUSDT → BTCUSDT for perp, BTCUSDT for spot) derived from the input symbol or hardcoded?

If hardcoded, make them derive from the input: `f"{symbol}" for perp, strip "USDT" + "USDT" for spot pair construction.

## 4. Fix Accept Modal Labels

GPT flagged that the accept modal labels crypto position size as "Contracts" (equity term). For BTC perps, "Contracts" is actually correct (perp futures ARE contracts). However, verify:

- The sizing logic calculates BTC perp contract size, not equity shares
- The modal shows relevant crypto fields (leverage, BTC size) not equity fields (options structure, expiry)
- If the modal is shared between equity and crypto, it should conditionally show the right fields based on `asset_class`

## 5. Update Documentation

### TODO.md
Mark Phase 2A-2D as complete. Update the Phase 2 section:

```markdown
## ✅ Phase 2: Crypto Scalper Review/Overhaul — COMPLETE

### ✅ Phase 2A — Plumbing & Auth (COMPLETE)
- [x] Ticker normalization (.P suffix handling)
- [x] Auth on BTC signal mutation routes
- [x] Legacy route coupling killed
- [x] Symbol propagation (selected coin → API)
- [x] Dead code cleanup, smoke tests

### ✅ Phase 2B — BTC Setup Engine (COMPLETE)
- [x] Crypto bias bypass (NEUTRAL alignment for crypto signals)
- [x] Holy Grail + Exhaustion PineScript alerts on BTCUSDT.P
- [x] 3 crypto-native strategies: Funding Rate Fade, Session Sweep, Liquidation Flush
- [x] Breakout position sizing (1% max risk, $25K account)
- [x] 5-minute scheduler, 24/7

### ✅ Phase 2B.5 — Market Structure Filter (COMPLETE)
- [x] Volume Profile (POC/VAH/VAL from klines)
- [x] CVD gate (flow confirmation/divergence)
- [x] Orderbook imbalance (bid/ask ratio + wall detection)
- [x] Score modifier: -45 to +35 per signal

### ✅ Phase 2C — Discord Delivery (COMPLETE)
- [x] Crypto-specific Discord embeds
- [x] 24/7 notifier cron
- [x] Take/Pass/Watching buttons (no committee)

### ✅ Phase 2D — Cleanup (COMPLETE)
- [x] Standalone crypto-scalper/ deleted
- [x] Orphaned references removed
- [x] Docs updated
```

### CLAUDE.md
Add Stater Swap to the architecture overview. Mention:
- Crypto signals route via `asset_class=CRYPTO` to Stater Swap UI
- BTC setup engine runs every 5 min on Railway
- Market structure filter (volume profile + CVD + orderbook) modifies crypto signal scores
- Holy Grail PineScript alerts also fire for BTCUSDT.P

### DEVELOPMENT_STATUS.md
Update with Phase 2 completion. Note the Breakout prop account context.

## 6. Verify No Broken Imports

After deleting `crypto-scalper/`, run the test suite to verify nothing imported from that directory:
```
py -m pytest tests -q
```

Also grep the codebase for any references to `crypto-scalper` or `crypto_scalper`:
```
Select-String -Path "C:\trading-hub\**\*.py" -Pattern "crypto.scalper" -Recurse
Select-String -Path "C:\trading-hub\**\*.js" -Pattern "crypto.scalper" -Recurse
```

## Definition of Done

- [ ] `crypto-scalper/` directory deleted from repo
- [ ] No orphaned references to standalone scalper in frontend or backend
- [ ] `crypto_market.py` uses symbol param throughout (not hardcoded BTC)
- [ ] Accept modal shows correct fields for crypto vs equity
- [ ] TODO.md updated with Phase 2 completion
- [ ] CLAUDE.md updated with Stater Swap architecture
- [ ] DEVELOPMENT_STATUS.md updated
- [ ] All tests pass
- [ ] No broken imports from deleted directory
