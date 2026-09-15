# Local machine read — the UW MCP connector exists; the RTH consumer does not live here

**CC-BUILD, 2026-09-15 03:09 ET. R-IV.384(b) / R-IV.388(c).** Read-only. No key, no env
contents, no command-line argument longer than 24 characters left unredacted.

---

## ⚠ THIS READ WAS TAKEN OUTSIDE RTH — AND THAT LIMITS WHAT IT CAN SAY

**The order specified "during today's RTH". It is 03:09 ET Tuesday.**

**A read taken now cannot characterise a consumer that runs 09:30–16:00.** That is the
Sunday mistake in its exact form — measuring a scheduled process at an hour it was never
scheduled to run, then reading the absence as evidence (Addendum 3, Law 2).

**So the findings below split in two:** the time-INDEPENDENT ones stand as taken; **the
connection-rate sample does not exist yet and must be retaken during RTH.**

## 1. THE UW MCP CONNECTOR IS CONFIGURED — present, not hypothesised

```
Claude Desktop MCP servers (names and command only):
  railway-mcp-server    npx    env_block=True
  ssh-vps               npx    env_block=True
  tradingview           uvx    env_block=False
  unusualwhales         npx    env_block=True      <-- HERE
```

**`unusualwhales` is configured, via `npx`, with an `env` block** — which is where an API
key would live. **It was named as a candidate; it is now established as existing.**

**It holds no connection at 03:09**, which is exactly what an on-demand, app-driven server
should look like at three in the morning. **That is consistent with the evening component
and proves nothing about it** — the disconnect hour is still the discriminator.

## 2. NO SCHEDULED RTH CONSUMER ON THIS MACHINE

**Scheduled tasks outside `\Microsoft\`, all of them, with triggers:** thirty entries —
Adobe, NVIDIA, OneDrive, Omen, Razer, HP, Mozilla, Google, Meta.

**Exactly one is trading-related:**

```
\TradingHub-PriceHistoryArchive    Ready    daily trigger @ 02:15
```

**02:15 is overnight, not a market-hours window.** **There is no scheduled task on this
machine with an RTH trigger.**

## 3. NO STRAY COPY OF THE KNOWN CLIENTS

**Scope: `C:\Users\nickh`, `C:\temp`, `C:\opt`, depth 6, excluding both repo trees.**

Searched for `flow_scanner*.py`, `uw_forward_logger`, `gen_vps_writer.py`. **None found
outside the repos.**

## 4. WHAT HOLDS UW CONNECTIONS AT 03:09

```
api.unusualwhales.com -> 104.26.5.177, 104.26.4.177, 172.67.70.143

ESTABLISHED, by owning process:
  pid 24052   chrome    conns=2    C:\Program Files\Google\Chrome\Application\chrome.exe
```

**Only Chrome.** No python, no node, no MCP server process.

**And Chrome is probably NOT the quota consumer.** The browser talks to
`unusualwhales.com` under a *session*, not the API token — and the limit that is being hit
is `x-uw-token-req-limit`, a token-scoped counter. **Probably, not certainly: nothing here
measures which credential those two connections carry**, and that is worth one line rather
than an assumption.

**The four `python` processes are all `tradingview-mcp`** — a different vendor entirely.

## What this read settles, and what it does not

| question | answer |
|---|---|
| Is there a second Railway instance? | **NO** — excluded R-IV.383(b) |
| Is there a scheduled RTH job on this machine? | **NO** |
| Is there a stray copy of the known clients here? | **NO**, in the stated scope |
| Does the UW MCP connector exist? | **YES**, configured with an env block |
| **What consumes ~1,345/h during RTH?** | **STILL UNANSWERED** |

**With Railway excluded and this machine showing no scheduled RTH consumer, the RTH
component has two remaining homes: the VPS — unreachable from here since Friday — or the
MCP connector being driven during market hours as well as in the evening.**

**The second is testable and cheap: the disconnect hour, if it is taken during RTH rather
than in the evening, separates both components at once.** A disconnect scheduled for the
evening tests only the evening.

## Owed

**The connection-rate sample, 10 minutes, during RTH** — process, connection count, and
rate. **It is the one part of this order that a 03:09 reading cannot substitute for**, and
I have not pretended otherwise.
