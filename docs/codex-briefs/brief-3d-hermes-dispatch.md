# Brief 3D: Hermes Dispatch — Weekly AI Performance Report

## Summary

Expand the existing Saturday VPS cron (`committee_review.py`) into a comprehensive weekly performance report. Hermes Dispatch synthesizes the full week's trading data into a multi-section Discord embed AND saves it to PostgreSQL for historical access in the Chronicle.

Depends on Briefs 3A (outcome data) and 3B (Oracle metrics).

## Current State

`committee_review.py` runs Saturday 9 AM MT. It computes basic analytics (override rates, timing buckets, conviction win rates) and posts a single Discord embed. Lessons are saved to `lessons_bank.jsonl`.

## Hermes Dispatch: Full Weekly Report

### Data Gathering

Hermes pulls from:
1. **Oracle cached payload** — strategy scorecards, decision quality, options analytics (from Redis)
2. **Ariadne's Thread** — resolved outcomes from the past 7 days (from signals table)
3. **Risk budget history** — peak risk exposure during the week (if tracked)
4. **Committee logs** — JSONL data from VPS for committee-specific analysis
5. **Lessons bank** — existing lessons for continuity

### Report Sections

```
📜 HERMES DISPATCH — Week of March 8-14, 2026
═══════════════════════════════════════════════

📊 PERFORMANCE SUMMARY
   Total P&L: +$580 (Equity: +$430, Crypto: +$150)
   Trades: 12 (8W / 4L = 66.7% win rate)
   Expectancy: $48.33/trade
   Max Drawdown: -1.8% (well within limits)

🏆 STRATEGY RANKINGS
   1. Holy Grail: A grade (4/4 wins, +$320)
   2. Funding Rate: B grade (2/3 wins, +$85)
   3. CTA Scanner: B- grade (1/2 wins, +$45)
   4. Session Sweep: F grade (1/3 wins, -$80)

🎯 DECISION QUALITY (Prometheus Report)
   Committee agreement: 78%
   Overrides: 2 (1 win, 1 loss = net +$35)
   Best override: NVDA TAKE (committee said PASS) → +$120
   Worst override: AAPL TAKE (committee said PASS) → -$85

📋 OPTIONS INTELLIGENCE (for equity trades)
   Avg DTE at entry: 32 days
   Avg DTE at exit: 18 days
   Best structure: Put debit spreads (3/4 wins)
   Exit quality: 60% early profit-take, 20% stopped out, 20% held

🔮 CASSANDRA'S MIRROR (what you missed)
   Passed signals that would have won: 4 (potential +$280)
   Passed signals that would have lost: 7 (avoided -$420)
   Net pass quality: GOOD (+$140 saved by passing)

💡 SOPHIA'S SCROLL (this week's lessons)
   1. Holy Grail on 1H BTC is more reliable than 15m — 4/4 vs signal noise
   2. Session Sweep needs minimum range filter — 2 of 3 losses were narrow Asia ranges
   3. Override when committee is LOW conviction has positive edge this month

📈 OUTLOOK
   Current bias: TORO MINOR (equity), RANGING (BTC)
   Risk budget: 68% remaining (equity), 82% remaining (crypto)
   Focus next week: Holy Grail continuation trades, avoid Session Sweep in quiet markets
```

### AI Synthesis

Use Claude Sonnet to generate the report from structured data. The sections above are filled by computation; Sonnet writes:
- The natural-language summary connecting the sections
- Sophia's Scroll lessons (distilled from patterns in the data)
- The Outlook section (forward-looking based on current regime + performance trends)

Cost: ~$0.02 per weekly report (Sonnet).

### System Prompt for Hermes

```
You are Hermes, the messenger of the trading gods. You deliver the weekly
performance dispatch for Nick's trading system.

Your report must be:
- Brutally honest: if something is failing, say so
- Specific: use exact numbers, ticker names, dollar amounts
- Actionable: every lesson should have a concrete next step
- Brief: no filler, no encouragement fluff, just facts and insights

Nick has ADHD — keep sections punchy, use the structured format provided.
Don't soften bad news. A losing week should feel like a losing week.

You will receive structured metrics. Generate:
1. Three distilled lessons from the week's data
2. A forward-looking outlook based on current regime and performance trends
3. One specific recommendation for next week
```

### Storage

Save the full report to PostgreSQL:

```sql
CREATE TABLE IF NOT EXISTS weekly_reports (
    id SERIAL PRIMARY KEY,
    week_of DATE NOT NULL,
    report_json JSONB NOT NULL,  -- full structured data
    narrative TEXT,               -- Hermes' synthesis
    lessons JSONB,               -- extracted lessons array
    total_pnl FLOAT,
    total_trades INT,
    win_rate FLOAT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Also continue writing to `lessons_bank.jsonl` on VPS for backward compatibility with committee context injection.

### Discord Delivery

Post as a multi-embed message to `#📊-signals` (or a dedicated `#weekly-report` channel):
- Embed 1: Performance Summary + Strategy Rankings
- Embed 2: Decision Quality + Options Intelligence
- Embed 3: Cassandra's Mirror + Sophia's Scroll + Outlook

Split into 3 embeds because Discord has a 4096-character limit per embed.

## Scheduler

Modify VPS cron for Saturday 9 AM MT:
```
# Hermes Dispatch — Saturday 9 AM MT (4 PM UTC)
0 16 * * 6 cd /opt/openclaw/workspace/scripts && /usr/bin/python3 hermes_dispatch.py >> /var/log/hermes_dispatch.log 2>&1
```

The script:
1. Fetches Oracle data from Railway Redis cache
2. Fetches resolved outcomes from Railway API
3. Computes week-over-week comparisons
4. Calls Sonnet for synthesis
5. Posts to Discord
6. Saves to Railway PostgreSQL
7. Writes lessons to local JSONL

## Files

| File | Change |
|------|--------|
| `scripts/hermes_dispatch.py` | NEW — replaces `committee_review.py` for weekly reports |
| `backend/database/postgres_client.py` | Add `weekly_reports` table migration |
| `backend/analytics/api.py` | Add `/weekly-reports` endpoint for Chronicle to consume |

## Definition of Done

- [ ] `hermes_dispatch.py` generates full weekly report
- [ ] Report includes: performance, strategy rankings, decision quality, options intel, counterfactuals, lessons, outlook
- [ ] Sonnet synthesizes lessons + outlook (~$0.02/report)
- [ ] Report saved to `weekly_reports` PostgreSQL table
- [ ] Report posted to Discord as multi-embed message
- [ ] Lessons also written to `lessons_bank.jsonl` for committee context
- [ ] VPS cron updated (Saturday 9 AM MT)
- [ ] Chronicle tab can display historical weekly reports
- [ ] All existing tests pass
