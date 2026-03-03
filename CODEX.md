# CODEX.md

**Codex is a backup builder.** Claude Code (via VSCode) is the primary implementation agent.

This file provides minimal guidance for OpenAI Codex when used as a fallback. For the full project context, **always read [CLAUDE.md](./CLAUDE.md)** — it is the canonical reference.

## Critical: Read These First

1. **`CLAUDE.md`** — Architecture, deployment targets, key files, commands, environment variables
2. **`PROJECT_RULES.md`** — Prime directive, bias hierarchy, trading rules, workflow
3. **`DEVELOPMENT_STATUS.md`** — What's built, what's in progress, known issues

## Quick Facts

- **Project**: Pivot — AI-powered Discord trading assistant for options swing trading
- **Repo**: `303webhouse/pandoras-box` (single `main` branch)
- **Backend**: Railway (auto-deploys on push to `main`)
- **Pivot II**: Hetzner VPS at `188.245.250.2`, code at `/opt/openclaw/workspace/`
- **VPS has NO git repo** — deploy via direct file edits + `systemctl restart openclaw`
- **LLM**: Anthropic API direct (Haiku for chat/analysis, Sonnet for synthesis). NOT OpenRouter, NOT Gemini.
- **Three VPS services**: `openclaw`, `pivot-collector`, `pivot2-interactions`
- **Local repo**: `C:\trading-hub` — the ONLY clone. Never create a second one.
- **Env var pattern**: Always `os.getenv("VAR") or default` (not `os.getenv("VAR", default)`)

Everything else lives in CLAUDE.md. Read it.
