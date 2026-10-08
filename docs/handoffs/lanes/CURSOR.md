# CURSOR lane — status

**Written:** 2026-10-07 18:23 MDT (2026-10-08 00:23 UTC)
**Worked against:** `origin/main` = `600694a`
**Worktree / branch:** `C:\th-cursor` on `claude/stater-r741-lsr` (this session was CC-STATER, R-IV.741).
**Hub at read time:** not re-timed this turn.

## Why this lane exists
Nick hits Claude rate limits after a few days of Claude.ai + Claude Code use. Cursor is
the overflow environment. CC-STATER also runs here on `claude/stater-*` branches (R-IV.628).

## This session
R-IV.741 for CC-STATER: `_make_request` tells our 40/min refuse apart from the
vendor's silence. `bias_scheduler.py` was not touched. Status of that work is in
`CC-STATER.md`. BUILD merges after SPINE's ruling; this lane does not push `main`.

## What the next Cursor session should do first
If the task is Stater: read `CC-STATER.md` and hold the r741 merge. Otherwise
pick work from a SPINE ruling that names this lane.
