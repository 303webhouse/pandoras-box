# OLYMPUS COMMITTEE — Updated Architecture

## Committee Members (4 Agents + Synthesizer)

```
                    Trade Signal / Question
                           │
                           ▼
    ┌──────────────────────────────────────────┐
    │              COMMITTEE                    │
    │                                           │
    │  ┌─────────┐  ┌─────────┐  ┌──────────┐ │
    │  │  TORO   │  │  URSA   │  │ TECHNICAL│ │
    │  │ (bull)  │  │ (bear)  │  │ ANALYST  │ │
    │  │         │  │         │  │ (options, │ │
    │  │ Makes   │  │ Makes   │  │  Greeks,  │ │
    │  │ the     │  │ the     │  │  trend,   │ │
    │  │ bull    │  │ bear    │  │  risk)    │ │
    │  │ case    │  │ case    │  │          │ │
    │  └────┬────┘  └────┬────┘  └─────┬────┘ │
    │       │            │             │       │
    │  ┌────┴────────────┴─────────────┴────┐  │
    │  │           PYTHIA                    │  │
    │  │     (Market Profile / TPO /         │  │
    │  │      Auction Theory specialist)     │  │
    │  │                                     │  │
    │  │  Reads market structure to           │  │
    │  │  determine: trending or             │  │
    │  │  bracketing? Fair value?             │  │
    │  │  Key structural levels?             │  │
    │  └────────────────┬───────────────────┘  │
    │                   │                       │
    └───────────────────┼───────────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │     PIVOT        │
              │  (brash NYer)    │
              │                  │
              │  Synthesizes     │
              │  all 4 agents,   │
              │  makes final     │
              │  call            │
              └──────────────────┘
```

## Role Summary

| Agent | Role | Lens | Personality |
|-------|------|------|-------------|
| **TORO** | Bull case analyst | Momentum, catalysts, trend alignment | Enthusiastic but honest — won't force a bull case that doesn't exist |
| **URSA** | Bear case analyst | Risk, headwinds, regime conflicts | Skeptical but fair — won't manufacture risks that aren't there |
| **Technical Analyst** | Options/risk/trend specialist | Greeks, IV, spreads, position sizing, trend-following TA | Precise, data-driven, professorial. The "math person." Mildly skeptical of Market Profile. |
| **PYTHIA** | Market Profile specialist | TPO, value area, auction theory, volume profile, market structure | 180 IQ, calm authority, sees markets as organic auctions. The "structure person." |
| **Pivot** | Synthesizer | Weighs all 4 agents, cuts through noise, makes the call | Brash New Yorker, cynical about narratives, colorful language, driven to find edge |

## Key Tension (By Design)

The **Technical Analyst** and **PYTHIA** will sometimes disagree. This is intentional and productive:

- TA says "trend is up, buy the pullback to the 20 SMA" — PYTHIA might counter "price is at VAH with a poor high, the auction is likely to rotate lower before continuing"
- PYTHIA says "market is balanced, sell the VA edges" — TA might counter "the SMA stack just went bullish, this isn't balance, it's the early stage of a new trend"

Pivot resolves these disagreements by weighing which framework better fits the current evidence.

## Changes from Prior Architecture

- **REMOVED:** Risk Assessor (standalone agent) — risk management and position sizing responsibilities absorbed into the Technical Analyst
- **ADDED:** PYTHIA (Market Profile specialist) — dedicated auction theory and structural analysis
- **REFINED:** Technical Analyst now explicitly owns options expertise, Greeks analysis, and risk parameters in addition to trend-following TA

## Standalone Conversation Mode

Both PYTHIA and the Technical Analyst can operate independently outside committee mode:
- Nick can talk directly to PYTHIA about Market Profile concepts, chart analysis, and structural reads
- Nick can talk directly to the TA about options strategy, Greeks, and risk management
- Nick can talk directly to TORO for bullish thesis building and opportunity identification
- Nick can talk directly to URSA for risk assessment, stress testing, and bias challenge
- Nick can talk directly to Pivot for unfiltered trade opinions with his brash New Yorker personality
- These conversations use the full skill files as system prompts

## Skill File Locations

| Agent | Skill File | Lines |
|-------|-----------|-------|
| TORO | `toro-bull-analyst/SKILL.md` | ~100 |
| URSA | `ursa-bear-analyst/SKILL.md` | ~120 |
| Technical Analyst | `technical-analyst/SKILL.md` | ~250 |
| PYTHIA | `pythia-market-profile/SKILL.md` | ~280 |
| Pivot | `pivot-synthesizer/SKILL.md` | ~150 |

## Deployed System Prompts

The committee pipeline uses shorter, focused system prompts in `deploy/committee_prompts_v2.py`. These are the prompts that actually run through OpenRouter during committee evaluations. The skill files above are supersets that add direct conversation mode, personality depth, and cross-references.

## Knowledge Architecture (Layered)

```
Layer 1: Committee Training Bible (89 rules)        ← Always in context
         docs/committee-training-parameters.md         ~300 lines, compact

Layer 2: Skill files (per-agent)                     ← Loaded when relevant
         100-280 lines each                            Personality + methodology + examples

Layer 3: Raw Stable education docs                   ← On request only
         Google Drive: The Stable > Education Docs     27 docs (PDFs/images)
         DO NOT put in Project files                   Too large for routine context
```

This layered approach keeps context lean for everyday chats while making deep source material available when building or refining strategies.
