# Brief: Signal Pipeline Upgrades — Whale + UW Flow + Grouped Trade Ideas

**Priority:** HIGH — Three tightly connected builds that close the biggest gaps in the signal pipeline.
**Target:** Railway backend (`backend/`) + Frontend (`frontend/`)
**Estimated time:** 2-3 hours total
**Prerequisites:** UW Watcher bold-markdown fix deployed (done March 11). Phase 0G tests passing.
**Reviewed by:** Olympus (trading analysis) + The Titans (software design)

---

## Overview

Three builds, executed in order:

1. **Whale Hunter → signals table** — Whale signals stop vanishing and become real trade ideas
2. **UW Flow threshold trigger** — High-conviction UW flow auto-creates trade idea signals
3. **Grouped Trade Ideas** — Frontend consolidates signals by ticker+direction with confluence badges

All three funnel through the existing `process_signal_unified()` pipeline. No new tables, no schema changes, no VPS work.

See full brief at: `/home/claude/brief-signal-pipeline.md` in the working session, or the complete content below.

---

*Note: This brief was reviewed by both Olympus (trading committee) and The Titans (software design team) with a double-pass process. Olympus set the trading parameters (thresholds, base scores, sorting weights). The Titans reviewed architecture, security, UX, and implementation details. Four clarification notes from the Titans final review are appended at the end.*

---

Full brief content is in the companion file pushed alongside this stub. CC should read `brief-signal-pipeline-upgrades-full.md` for the complete implementation spec.