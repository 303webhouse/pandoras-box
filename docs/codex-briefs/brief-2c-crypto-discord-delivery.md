# Brief 2C: Crypto Signal Delivery to Discord

## Summary

Deliver crypto setup signals to Discord so Nick sees them on his phone, not just the Stater Swap dashboard. Lightweight alerts only — no committee review (too slow for scalping). Signals go to the existing `#📊-signals` channel with a distinct crypto visual style so they're instantly distinguishable from equity signals.

## Architecture

The crypto setup engine (`crypto_setups.py`) and TradingView webhook handler (`tradingview.py`) both call `process_signal_unified()` to write signals. The signal notifier (`signal_notifier.py`) already polls for new signals and posts to Discord. The question is whether the existing notifier handles crypto signals correctly or needs modification.

## Step 1: Check Signal Notifier Compatibility

Examine `scripts/signal_notifier.py` on VPS (`/opt/openclaw/workspace/scripts/signal_notifier.py`). It polls Railway for new signals and posts Discord embeds. Check:

1. Does it filter by `asset_class`? If it only fetches `EQUITY` signals, crypto signals will be invisible.
2. Does the embed format work for crypto? Equity signals show options-specific fields (expiry, strikes). Crypto signals need different fields (funding rate, session, position size in contracts, leverage).
3. Does it run during crypto hours? The cron is `*/15 14-21 * * 1-5` (market hours, weekdays only). Crypto is 24/7.

## Step 2: Crypto Signal Discord Embed

Create a crypto-specific embed format. The notifier should detect `asset_class=CRYPTO` and use a different embed builder.

### Embed Design

```
🟢 LONG BTCUSDT | Funding Rate Fade          (or 🔴 SHORT)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Entry: $84,250  |  Stop: $83,997  |  Target: $84,670
R:R: 1.7:1  |  Risk: $253 (1.0%)

📊 Market Structure: STRONG
   POC: $84,100 | CVD: BULLISH | Book: BID_HEAVY

💰 Breakout Sizing
   Size: 0.29 BTC (2.4x leverage)
   Risk: $250 / $25,000 = 1.0%

⏰ Session: London Open | Score: 78
```

Key differences from equity embeds:
- No options fields (no expiry, strikes, structure)
- Shows leverage and BTC contract size instead
- Market structure context (from Brief 2B.5) if available
- Session label (Asia/London/NY)
- Breakout account risk calculation

### Color Coding
- LONG = green embed sidebar
- SHORT = red embed sidebar
- Market structure STRONG = green dot
- Market structure WEAK/AVOID = orange/red dot

## Step 3: Cron Schedule for Crypto

The signal notifier cron needs to run during crypto hours (24/7, not just equity market hours).

Two options:

**Option A (recommended): Separate crypto notifier cron**
Add a new cron entry that runs a crypto-specific check:
```
# Crypto signal notifier — every 5 min, 24/7 (crypto never sleeps)
*/5 * * * * cd /opt/openclaw/workspace/scripts && /usr/bin/python3 signal_notifier.py --crypto >> /var/log/crypto_notifier.log 2>&1
```

Add a `--crypto` flag to `signal_notifier.py` that:
- Only fetches signals with `asset_class=CRYPTO`
- Uses the crypto embed format
- Posts to the same `#📊-signals` channel (or a dedicated `#crypto-signals` channel if Nick prefers)

**Option B: Modify existing notifier to handle both**
Change the existing notifier to fetch all signals regardless of asset_class and format them accordingly. Downside: the equity cron schedule (weekday market hours) would miss crypto signals outside those windows.

Use Option A — cleaner separation, correct schedule.

## Step 4: Discord Channel Decision

Two options for where crypto signals land:

**Option A: Same `#📊-signals` channel** — simpler, everything in one place, but might get noisy if both equity and crypto signals fire simultaneously.

**Option B: New `#crypto-signals` channel** — clean separation, Nick can mute one without losing the other. Requires creating the channel and adding its ID to the VPS config.

Implement for `#📊-signals` first (same channel). Nick can split later if it gets noisy. Use the distinct embed styling to differentiate.

## Step 5: Analyze Button Integration

Crypto signals should NOT have the "Run Committee" / "Analyze" button that equity signals get. The committee is too slow for crypto scalping. Instead, crypto signal embeds should have:

- **Take** — Nick will execute manually on Breakout/exchange
- **Pass** — Skip this signal
- **Watching** — Monitoring, not taking yet

These buttons should log decisions the same way equity buttons do (to `decision_log.jsonl` via the interaction handler), but should NOT trigger a committee run.

## Step 6: VPS Deployment

The notifier script lives on VPS. After code changes:
1. Push to repo (`scripts/signal_notifier.py`)
2. Download to VPS: `curl -s https://raw.githubusercontent.com/.../signal_notifier.py -o /opt/openclaw/workspace/scripts/signal_notifier.py`
3. `chown openclaw:openclaw /opt/openclaw/workspace/scripts/signal_notifier.py`
4. Add new cron entry for crypto schedule
5. Test: manually run `python3 signal_notifier.py --crypto` and verify embed appears in Discord

## Out of Scope

- Committee review for crypto signals (intentionally excluded — too slow)
- Push notifications / mobile alerts beyond Discord (Discord app handles this)
- Auto-execution on Breakout exchange (signals are manual execution only)
- Dedicated `#crypto-signals` channel (can add later if `#📊-signals` gets noisy)

## Definition of Done

- [ ] Signal notifier detects `asset_class=CRYPTO` and uses crypto embed format
- [ ] Crypto embeds show: entry/stop/target, R:R, market structure context, Breakout sizing, session
- [ ] Crypto notifier cron runs 24/7 every 5 minutes
- [ ] Take/Pass/Watching buttons on crypto embeds (no Analyze/Committee button)
- [ ] Decision logging works for crypto signals
- [ ] Deployed to VPS with correct cron schedule
- [ ] Test signal appears in Discord with correct formatting
