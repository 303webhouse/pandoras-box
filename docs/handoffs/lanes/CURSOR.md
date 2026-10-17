# CURSOR lane — status

**Written:** 2026-10-17 02:40 MDT (2026-10-17 08:40 UTC)
**Worked against:** `origin/main` = `f9f67c4d`
**Worktree / branch:** `C:\th-cursor` on `claude/stater-r1197-report` (this session was CC-STATER, R-IV.1197).
**Hub at read time:** healthy, build `f9f67c4d`.

## Why this lane exists
Nick hits Claude rate limits after a few days of Claude.ai + Claude Code use. Cursor is
the overflow environment. CC-STATER also runs here on `claude/stater-*` branches (R-IV.628).

## This session
R-IV.1197 for CC-STATER, report only. The 7-day collection report (liquidations, oi_change_4h,
oi_extreme per symbol), current data health, /stater section status, the SG-1 gate and the
paid-feed answer are in `CC-STATER.md`. No code, threshold or schema changed. The earlier docs
branch `claude/stater-r753-dates` was already merged. BUILD merges; this lane does not push `main`.

## What the next Cursor session should do first
If the task is Stater: read `CC-STATER.md` and wait for SPINE's ruling on its threshold
proposals. Otherwise pick work from a SPINE ruling that names this lane.
