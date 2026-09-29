# CURSOR lane — status

**Written:** 2026-09-29 07:27 MDT (13:27 UTC)
**Worked against:** `origin/main` = `1810006` (test(clock): a factor stamped from a local clock now fails a test)
**Worktree / branch:** `C:\th-cursor` on `cursor/lane-setup`
**Hub at read time:** `/health` healthy, build `1810006`, UW quota 5% used, Triton grader last ran session 2026-09-28

## Why this lane exists

Nick hits Claude rate limits after a few days of Claude.ai + Claude Code use. Cursor is
the overflow environment and a home for new modules that do not intersect the CC lanes.
It must be able to hand work back and forth with those lanes.

## What this session did (setup only; no application code touched)

- **Pandora MCP in Cursor.** `~/.cursor/mcp.json` (user-level, outside the repo) now
  carries `pandora-hub` (the hub's `/mcp/v1` URL, GitHub OAuth, no secrets in the file)
  plus the same `postgres` / `redis` / `ssh-vps` servers Claude Code uses from the
  gitignored `.mcp.json`. Cursor discovered all four live. The hub needs one GitHub
  OAuth approval in the browser as `303webhouse` before its tools appear.
- **Skills.** `~/.cursor/skills/<agent>` is a directory junction to `skills/<agent>/`
  for all eleven Olympus + Titans agents. Verified byte-identical (after LF
  normalisation) to the copies Claude Desktop syncs from Claude.ai, so Cursor and
  Claude.ai are running the same skill text.
- **Lane charter.** `.cursor/rules/cursor-lane.mdc` (always-applied Cursor rule).
- **Cross-environment memory.** This directory (`docs/handoffs/lanes/`) and its
  `README.md` protocol; `AGENTS.md` and `CLAUDE.md` now point here instead of the
  retired `docs/session-handoff.md`. A pointer file was added to the Claude Code local
  memory directory so CC lanes learn this lane exists without a commit.

## In flight

- PR from `cursor/lane-setup` → `main` carrying the files above. Docs/config only; a
  merge redeploys the app (every push to `main` does) but changes no runtime behaviour.
- `pandora-hub` OAuth approval pending Nick's click.

## Findings for other lanes (relayed here as text; owners insert)

- **Repo visibility reads PUBLIC** on 2026-09-29 07:20 MDT (`gh repo view --json
  visibility`). The local memory note of 2026-09-22 says PRIVATE. One of the two is
  stale; the SPINE handoff's "confirm the repo is private" item is still open.
- `docs/reference/key-files.md` and `DEVELOPMENT_STATUS.md` still describe Polygon
  (dead code since 2026-04-27) and the VPS committee scripts (VPS dead for months) as
  live. Doc rot, not a defect; a candidate for this lane if BUILD relays it.
- `backend/hub_mcp/README.md` tool table is missing the five tools added since
  2026-07-14 (its own note says so). Same class.

## What the next Cursor session should do first

1. Confirm the `pandora-hub` MCP is authenticated: call `mcp_ping`, then
   `mcp_describe_tools`, and note the tool count here.
2. Check whether the setup PR merged; if so, `git -C C:\th-cursor fetch` and rebase or
   start a fresh `cursor/<topic>` branch from `origin/main`.
3. Pick work only from the "Cursor-safe" list in the README ownership table or from a
   SPINE ruling that names this lane. Default: analysis passes (Olympus/Titans with hub
   data) and new-files-only modules.
