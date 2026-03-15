# Trading Team — Architecture Reference

Read this when working on the committee pipeline, agents, decision tracking, or outcome analysis.

---

## Pipeline

```
Signal arrives (webhook/scanner)
  → Gatekeeper (score + filter)
  → Context Builder (market data + bias + positions + whale + twitter + lessons)
  → 4 LLM Agents:
      TORO (bull) — finds reasons to take the trade
      URSA (bear) — finds reasons to pass
      TECHNICALS (risk/structure) — entry/stop/target/size
      PIVOT (synthesizer) — final recommendation
  → Discord embed with Take/Pass/Watching/Re-evaluate buttons
  → Nick decides → Decision logged
  → Nightly outcome matching (11 PM ET)
  → Saturday weekly self-review (9 AM MT)
  → Lessons fed back into future committee context
```

**Where:** VPS at `/opt/openclaw/workspace/scripts/`
**LLM:** Anthropic API direct — Haiku for TORO/URSA/TECHNICALS, Sonnet for PIVOT (~$0.02/run)
**Training Bible:** `docs/committee-training-parameters.md` (89 rules, cited by rule number)

---

## Brief Chain

| Brief | Scope | Status |
|-------|-------|--------|
| 03A | Gatekeeper, context builder, orchestrator, JSONL logging, dedup | ✅ Live |
| 03B | 4 LLM agent prompts, parsers, embed builder, cost controls | ✅ Live |
| 03C | Button handlers, decision logging, pushback/re-evaluation | ✅ Live |
| 04 | Outcome tracking, pattern analytics, weekly self-review | ✅ Live |
| 05A | Gatekeeper transparency, override feedback enrichment | ✅ Spec written |
| 05B | Adaptive calibration — dynamic thresholds + agent trust | Planned |

For current build/deploy status: `docs/TRADING_TEAM_LOG.md`

---

## Key Build Deviations

- **03B:** Sequential LLM calls via synchronous urllib (not async parallel) — ~40s per committee run. `call_agent()` blocks during calls.
- **03C:** `committee_interaction_handler.py` is a separate persistent bot (own systemd service `pivot2-interactions.service`), not merged into `committee_decisions.py`.
- **04:** All functions synchronous. Model ID `anthropic/claude-sonnet-4.6`. Discord posting uses bot token + REST API.

---

## Schemas

### committee_log.jsonl
```json
{
  "timestamp": "ISO8601",
  "signal_id": "sig_xxx",
  "signal": { "ticker": "...", "direction": "...", "alert_type": "...", "score": 75 },
  "context_snapshot": { "price": 590.5, "bias": "TORO MINOR" },
  "agents": {
    "toro": { "analysis": "...", "conviction": "HIGH" },
    "ursa": { "analysis": "...", "conviction": "LOW" },
    "risk": { "entry": "...", "stop": "...", "target": "...", "size": "..." },
    "pivot": { "synthesis": "...", "action": "TAKE", "conviction": "HIGH", "invalidation": "..." }
  },
  "nick_decision": null
}
```

### decision_log.jsonl
```json
{
  "timestamp": "ISO8601",
  "signal_id": "sig_abc123",
  "ticker": "SPY",
  "committee_action": "PASS",
  "committee_conviction": "MEDIUM",
  "nick_decision": "TAKE",
  "is_override": true,
  "decision_delay_seconds": 45.2
}
```

### outcome_log.jsonl
```json
{
  "signal_id": "sig_abc123",
  "result": "WIN",
  "pnl_category": "HIT_T1",
  "max_favorable_pct": 2.3,
  "max_adverse_pct": 0.8,
  "risk_reward_achieved": 1.85,
  "committee_was_right": true,
  "override_correct": null
}
```

### lessons_bank.jsonl
```json
{
  "lesson": "HIGH conviction signals won 80% vs 45% for LOW",
  "week_of": "2025-02-22",
  "total_signals": 15
}
```

---

## File Paths (VPS)

| File | Purpose |
|------|---------|
| `scripts/pivot2_committee.py` | Orchestrator + gatekeeper + whale context fetch |
| `scripts/committee_context.py` | Market data enrichment + bias challenge + lessons + twitter + whale |
| `scripts/committee_prompts.py` | 4 agent system prompts (Bible-referenced) |
| `scripts/committee_parsers.py` | `call_agent()` + response parsers (Anthropic API direct) |
| `scripts/committee_decisions.py` | Decision logging, disk-backed pending store, button components |
| `scripts/committee_interaction_handler.py` | Persistent Discord bot for buttons, modal, reminders |
| `scripts/committee_outcomes.py` | Nightly outcome matcher + Railway API fetcher |
| `scripts/committee_analytics.py` | Pattern analytics computation |
| `scripts/committee_review.py` | Weekly self-review LLM + Discord + lessons bank |
| `scripts/committee_autopsy.py` | Post-trade narrative generation (Haiku) |
| `data/committee_log.jsonl` | Committee run history |
| `data/decision_log.jsonl` | Nick's decisions |
| `data/outcome_log.jsonl` | Matched outcomes |
| `data/lessons_bank.jsonl` | Distilled lessons |

---

## Integration Contracts

**03A → 03B:** `build_committee_context(signal) → dict`, `format_signal_context(signal, context) → str`, `log_committee()`

**03B → 03C:** `call_agent(system_prompt, user_message, max_tokens, temperature, agent_name, model) → str`, parser functions, prompt constants, `build_committee_embed()`

**03C → 04:** `decision_log.jsonl` entries, `pending_recommendations` disk store, `log_decision()`

**04 → feedback loop:** `outcome_log.jsonl`, `lessons_bank.jsonl`, `compute_weekly_analytics(days=7) → dict`, Railway endpoint `GET /webhook/outcomes/{signal_id}`
