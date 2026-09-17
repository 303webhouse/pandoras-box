# VERIFICATION LAWS — INSTANCE: A DEPLOY SCRIPT IS NOT A PROCESS

**Filed:** CC-BUILD, 2026-09-17, on R-IV.438(a).
**Class:** the same family as the readiness gate (liveness vs identity) and the prescribed
instrument — **an artifact was read as evidence of a running system.**

> **A DEPLOYMENT SCRIPT IS A CLAIM ABOUT THE PAST, NOT EVIDENCE OF THE PRESENT.**
> It proves that someone intended a thing to run, on some day, in some shape. It proves nothing
> about whether it ran, whether it still runs, or whether the host exists.

## WHAT HAPPENED

`gen_vps_writer.py` deploys a complete UW collector tree to a Hetzner box. From that file the
board derived: a second UW client, its throttle constants, a pacing arithmetic of 1,440 calls an
hour, **86% of the account limit**, and an explanation for the GEX outage. Those figures entered
R-IV.369, R-IV.370, R-IV.371, the transfer plan and the sinks brief, and were cited for six days.

**The box has been unpaid and inactive for months. Nothing in that tree ever ran.**

**Every lane made the same move, including spine and including this one.** The DEF that recorded
it even carried the caveat — *"an identification from the deploy script, not an observation of a
running process"* — and the number travelled anyway. **A caveat beside a figure does not stop
the figure travelling; only a check that can fail does.**

## WHY THE USUAL CHECKS DID NOT CATCH IT

- **The host was unreachable, and unreachable was read as "firewalled", not "absent".** Ports
  22/443/80 timing out is consistent with a live box behind a deny-all rule AND with no box at
  all. The two were never separated, and the cheaper reading won.
- **The repo agreed with itself.** The deploy script, the systemd units in CLAUDE.md, and the
  cron manifest all describe the same system, so every cross-check inside the repo confirmed it.
  **Agreement among artifacts of one origin is not corroboration** (Law 2).
- **The consequence looked like the cause.** Unattributed quota existed, and the arithmetic
  matched to a plausible fraction. A number that fits is not a number that is measured.

## THE CHECK THAT WOULD HAVE FAILED

**Ask the host to prove it is alive, in a way only a running process can answer.** Not a port
scan, not a config file: a request that reaches the process, a log line with a recent timestamp
read from the box, a row written by it in the last hour, or — cheapest here — **the vendor's own
account counter attributed to a second key**. None existed, and none was asked for.

For a cost claim specifically: **an attribution to a host must cite an artifact the host itself
produced.** A file in this repo is an artifact this repo produced.

## WHAT ELSE WAS ATTRIBUTED TO THAT BOX (R-IV.438(d)(e))

**The Discord bot.** CLAUDE.md's own rule puts the single bot instance on the VPS. Confirmed
from the deploy surface, not from the rule: `Procfile` declares `worker: python
run_discord_bot.py`, and Railway runs **two services — `pandoras-box` and `Postgres`, no
worker** — so the bot has no home there either. **The bot has not run in production, and the
alert path that depends on it has been absent, not merely quiet.**

**What still works, because it never needed the bot:** every hub-side Discord delivery is a
WEBHOOK (`DISCORD_WEBHOOK_ALERTS`, `DISCORD_WEBHOOK_SIGNALS`, the Hermes catalyst path), posted
by the hub process itself. The supervision brief's delivery design (R-IV.372) can therefore live
there.

**What silently has no producer:** the pivot-key ingestion endpoints the VPS collector was to
feed — `POST /api/uw/flow` (writes `uw:flow:{SYMBOL}` for the frontend's flow context) and the
consolidated `POST /ticker-updates` handler. The hub's own `uw_flow_poller` writes `flow_events`
directly and is unaffected; the Redis flow-context keys have no live writer. **An endpoint with
no producer answers "available: false" forever, which reads as a quiet feature rather than an
absent one.**
