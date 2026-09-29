# AGENTS.md

## Session continuity
- Keep project files current as work is done; do not defer documentation or backfill.
- When code changes affect behavior, update the relevant docs, config, and examples in the same session.
- Before ending the session, rewrite your lane's status file in `docs/handoffs/lanes/`
  (protocol in `docs/handoffs/lanes/README.md`). `docs/session-handoff.md` is retired
  (last entry 2026-02-26) — do not append to it.
- Read every file in `docs/handoffs/lanes/` at session start. Several environments
  (Claude.ai, Claude Code, Cursor) work this repo; that directory is how they see each other.
