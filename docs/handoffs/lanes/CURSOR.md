# CURSOR lane — status

**Written:** 2026-10-07 16:33 MDT (2026-10-07 22:33 UTC)
**Worked against:** `origin/main` = `db1d864`
**Worktree / branch:** `C:\th-cursor` on `claude/stater-r707-liq` (this session was CC-STATER, R-IV.727).
**Hub at read time:** not re-timed this turn.

## Why this lane exists
Nick hits Claude rate limits after a few days of Claude.ai + Claude Code use. Cursor is
the overflow environment. CC-STATER also runs here on `claude/stater-*` branches (R-IV.628).

## This session
R-IV.727 for CC-STATER: units settled USD, so Coinalyze-sourced liquidations, open_interest,
and oi_extreme score again. One commit after `ff25480` (R-IV.728). Status of that work is
in `CC-STATER.md`. BUILD merges; this lane does not push `main`.

## What the next Cursor session should do first
If the task is Stater: read `CC-STATER.md`. If merge is pending, do not add a second
commit on `claude/stater-r707-liq`. Otherwise pick work from a SPINE ruling that names
this lane.
