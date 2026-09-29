# Lane status files — cross-environment memory

This directory is the memory that travels with the repo between the three
environments that work on Pandora's Box: **Claude.ai** (SPINE, Trade Analysis),
**Claude Code in VS Code** (the CC-* lanes) and **Cursor** (the CURSOR lane).
`docs/session-handoff.md` was the previous attempt at this; its last entry is
2026-02-26 and it is retired in favour of per-lane files.

## Protocol

1. **One file per lane, one author per file** (conventions #9). `CC-BUILD.md` is
   written only by CC-BUILD; `CURSOR.md` only by Cursor. Another lane's facet is
   relayed as text for the owner to insert.
2. **Whole-file rewrite at session end**, not an append (conventions #13). The file is
   a *current state*, not a log. History is in git.
3. **Every file carries:** the `origin/main` SHA the session worked against, the date
   (Mountain Time, with UTC beside it), what changed, what is in flight, and the one
   thing the next session should do first.
4. **Public-safe only.** This repository has been PUBLIC for most of its life and its
   visibility must be checked, not assumed (`gh repo view --json visibility`). No
   balances, positions, P&L, account identifiers, open routes, credentials, or broker
   document contents. Book figures live in the Claude.ai Project and the local memory
   directory, never here.
5. **Read all of them at session start**, newest first. A lane that starts without
   reading the board is the lane that steps on another lane's file.

## Two channels, by sensitivity

| Channel | Where | Reaches | May hold book figures? |
|---|---|---|---|
| Lane status files | `docs/handoffs/lanes/*.md` (this dir) | every environment via git; Claude.ai via GitHub read | **No** |
| Local memory | `C:\Users\nickh\.claude\projects\C--trading-hub\memory\` (`MEMORY.md` is the index) | Claude Code and Cursor on this machine, no commit needed | Yes |
| Claude.ai Project memory | the Pandora's Box Project in Claude.ai | SPINE / Trade Analysis only; Nick ferries pastes | Yes |

A durable learning that both local environments need goes in the local memory
directory as a new file with one index line in `MEMORY.md`. A status update that
every environment needs goes here.

## Lane ownership (from the SPINE handoff of 2026-09-22)

| Lane | Runs in | Owns | Rulings numbered |
|---|---|---|---|
| SPINE | Claude.ai | the queue; issues rulings; writes no code | `R-IV.###` |
| Trade Analysis | Claude.ai | book *decisions*, Olympus passes, bucket tags | `TA-###` |
| CC-BUILD | Claude Code | backend code, migrations, deploys, most `docs/` | — |
| CC-QUERY | Claude Code | read-only DB reads, measurement, studies | — |
| CC-POSITIONS | Claude Code | book writes, broker reconciliation, book DEFs | — |
| CC-ABACUS | Claude Code (`C:\th-abacus`) | `/app/abacus`, v2 frontend, `v2.css`/`v2.js`, design tokens | — |
| CURSOR | Cursor (`C:\th-cursor`) | see `CURSOR.md`; new-files-first; branch + PR only | — |

Lanes talk only through SPINE or via cc'd relays (`docs/codex-briefs/RELAY_*.md`).
The shared checkout `C:\trading-hub` is sync-and-package only; every lane builds in
its own worktree and files to `main` by pathspec-scoped commit or PR.
