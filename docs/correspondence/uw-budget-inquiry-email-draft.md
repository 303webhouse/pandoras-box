# UW Historical Access — Budget Inquiry Email Draft

**To:** dev@unusualwhales.com
**Status:** READY TO SEND. Non-blocking, parallel track to Phase 0.5 deployment.
**Purpose:** Resolve §12-RES-4 of the Titans backtest review by getting actual pricing data on expanded historical REST access.

---

## Email Draft

**Subject:** Historical data access pricing inquiry — basic plan user looking to upgrade

**Body:**

Hi UW team,

I'm a basic-plan API customer running a quantitative backtest project on options-flow-augmented strategies, and I'm hitting the 30-trading-day historical cap on flow alerts, dark pool, net-premium ticks, and intraday greek-exposure.

I did notice the bare `/greek-exposure` endpoint returns ~1 year of daily history without a date parameter — that carve-out is great, thank you.

The error response on capped endpoints pointed me here to discuss pricing for full historical access. My use case is:

- Retrospective backtesting of options-flow-augmented trading strategies (1-5 year lookback ideal)
- Daily aggregation — I don't need tick-level resolution for the backtest, just enough depth to validate flow-filter hypotheses against historical setups
- Single-user access (not a team or redistribution)
- Willing to build cache-first architecture so I'm not hammering your API for every backtest run

Could you share pricing for a plan tier that unlocks expanded REST historical depth for the following endpoints?

- `/api/stock/{ticker}/flow-alerts`
- `/api/darkpool/{ticker}`
- `/api/stock/{ticker}/net-prem-ticks`
- `/api/stock/{ticker}/spot-exposures`

If there's a tier with ≥18 months depth on these endpoints, I'd like to know what it costs. Also curious whether your $250/mo historical options trades parquet product (mentioned on api.unusualwhales.com/docs) is a viable substitute for any of the above.

Thanks for any info you can share.

Nick Hertzog

---

## Send Instructions

1. Use your normal email client. No special routing needed.
2. Don't mention "Claude" or "AI agents" in the body — the ask is about data access pricing, nothing else.
3. When they reply, paste the reply back to me and I'll integrate it into §12-RES-4 of the Titans review + the findings doc.
4. Expected turnaround: 1-3 business days for a reply from UW's team. This does NOT block Phase 0.5 deployment — the logger cron ships regardless.

---

**Status: ready to copy-paste and send whenever.**
