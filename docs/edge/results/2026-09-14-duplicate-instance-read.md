# Duplicate-instance read — no second Railway deployment holds the key

**CC-BUILD, 2026-09-14. R-IV.383(b).** Read-only. No project link was changed for the
hub; the other projects were inspected from a scratch directory with its own link, and
`fabulous-essence / production / pandoras-box` was verified intact afterwards.

---

## The listing

**SCOPE, per conventions #10: every project on the account `303webhouse's Projects`,
every environment in each, every service instance in each environment.**

```
fabulous-essence       production    pandoras-box    SUCCESS  repo 303webhouse/pandoras-box
                                     Postgres        SUCCESS  postgres-ssl:17
enchanting-ambition    production    — NO SERVICES —
writer-studio          production    writer-studio-app  SUCCESS
                                     Postgres        SUCCESS  postgres-ssl:18
```

**One environment per project. One hub instance. No staging, no preview, no second
`pandoras-box`.**

## The key

**`writer-studio-app` holds NO UW variable of any kind** — checked by name, against
`UW_API_KEY`, `UNUSUAL_WHALES_API_KEY` and any `UW_*`. **`enchanting-ambition` has no
service to hold one.**

## Verdict

**THE DAYTIME CONSUMER IS NOT A SECOND RAILWAY DEPLOYMENT.** The hypothesis is excluded,
not merely unsupported.

**What remains, and what the exclusion is worth:** the RTH component runs somewhere that is
not this Railway account. That leaves the VPS — still unreachable from this workstation —
and the principal's own machine or app. **The disconnect hour (R-IV.383(d)) separates the
evening component; it does not address the RTH one, and after this read the RTH component
has no candidate on infrastructure I can see.**

**Stated plainly because a negative read is easy to over-claim:** this rules out a
duplicate on Railway. **It does not rule out a duplicate anywhere else**, and the two
places I cannot see are exactly the two places left.
