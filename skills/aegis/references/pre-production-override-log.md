# AEGIS Pre-Production Override Log

Running record of every pre-production override invoked per `skills/_shared/TITANS_RULES.md § Veto Rights`.

**Purpose:** When Nick invokes the pre-production override on an AEGIS data-API credential flag, the flag is recorded here — the override is acknowledgment, not dismissal. Every entry feeds into the comprehensive security review backlog.

**Override eligibility:** Data-API credentials only (UW API key, alternative data sources). Broker/trading API credentials (Robinhood, IBKR, Fidelity, Breakout Prop) are NOT eligible regardless of phase.

**Override expiry triggers:**
1. Any broker trading API is connected to the hub.
2. Nick formally schedules the comprehensive security review.

When either trigger fires, all overrides expire and the recorded flags become active review items.

---

## Override entries

_No overrides recorded yet._

<!-- Entry format:
### YYYY-MM-DD — [build name / brief ID]
- **Flag:** [original AEGIS finding]
- **File:line:** [where the flag fires]
- **Override conditions at invocation:** [broker connected? security review scheduled?]
- **Nick written acknowledgment:** [link to chat transcript or commit comment]
- **Resolution plan:** [what gets fixed in the comprehensive security review]
-->
