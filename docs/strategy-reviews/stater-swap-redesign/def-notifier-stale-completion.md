# DEF-NOTIFIER-STALE — Completion Note (2026-07-20 UTC)

Opened per Fable's S-4 sequencing ruling (2026-07-19), following S-4 Phase 0's finding (0.3): the VPS-deployed `scripts/signal_notifier.py` was a stale 382-line pre-crypto version, never updated since the local repo's 577-line crypto-aware rewrite. The `--crypto` cron flag had been a silent no-op since inception.

## Deploy

**Mechanism (disclosed per instruction):** direct `scp` from the local machine to the VPS, using the same key (`~/.ssh/id_rsa`) as the `ssh-vps` MCP connector, targeting `/opt/openclaw/workspace/scripts/signal_notifier.py`. Chosen over reconstructing the file via an SSH heredoc for byte-exact fidelity — this session has hit repeated LF/CRLF issues on Windows, and a hash-verified binary-safe transfer avoids that risk entirely.

Pre-deploy: backed up the stale file in place (`signal_notifier.py.pre-crypto-backup-20260719`, not deleted) before overwriting — reversible, matches this program's standing "don't discard on top of unfamiliar state" discipline.

## Gate 1 — file hash matches repo HEAD: PASS

| | local (repo HEAD) | VPS (post-deploy) |
|---|---|---|
| SHA-256 | `32f52e5c20320e1c36de3fee55e672f8e9e34d0c8ab10fc3497e5a65199aba79` | `32f52e5c20320e1c36de3fee55e672f8e9e34d0c8ab10fc3497e5a65199aba79` |
| lines | 577 | 577 |

Exact match. Also confirmed the deployed file compiles clean (`py_compile` + `ast.parse`, no syntax errors) before waiting on the cron.

## Gate 2 — next crypto cron cycle exercises the new code: PASS (with an honest caveat)

Watched `/var/log/crypto_notifier.log` live across the deploy boundary. Clean before/after:

```
# 00:20:02Z (pre-deploy, old 382-line script)
{"ok": true, "timestamp": "...", "signals_fetched": 0, "new_signals": 0,
 "alerts_posted": 0, "skipped_old": 0, "skipped_non_trade": 0}

# 00:25:02Z (post-deploy, new 577-line script)
{"ok": true, "mode": "crypto", "timestamp": "...", "signals_fetched": 0,
 "new_signals": 0, "alerts_posted": 0, "skipped_old": 0,
 "skipped_non_trade": 0, "skipped_wrong_class": 0}
```

The `"mode"` and `"skipped_wrong_class"` fields are new-code-only — the old 382-line script had no `argparse`, no `crypto_mode` concept, and structurally could not have produced this JSON shape. This is unambiguous proof the new code is live and running cleanly on the VPS (no crash, no import errors).

**Caveat, reported honestly rather than overclaimed:** `post_crypto_signal_alert()` itself was NOT literally invoked on this tick — `signals_fetched: 0`, so the per-signal loop body (where `is_signal_crypto()`/`post_crypto_signal_alert()` are called) never executed. Checked why: the one currently-`ACTIVE` crypto signal (`CRYPTO_Session_Sweep_BTCUSDT_1784472643`, the same row that satisfied DEF-ENRICH-CLOBBER's sentinel) is already present in `seen_signal_ids.json` — processed once by the old script before today's deploy, so both old and new code skip it identically (`if signal_id in seen_set: continue`, before the crypto-routing check is ever reached). No newer crypto signal has fired since. Full exercise of `post_crypto_signal_alert` awaits a genuinely new crypto signal, which isn't forceable on demand and wasn't attempted (no synthetic signal injected, matching this session's established practice of not manufacturing test data on a live production surface without explicit sign-off).

## Gate 3 — report readiness for Nick's Discord eyeball

**Infrastructure is ready, not yet exercised end-to-end.** The new code is deployed, verified byte-identical to repo HEAD, and running cleanly on its 5-minute cadence. The moment a new crypto trade signal fires (`Crypto Scanner`, `Session_Sweep`, or the newer `CVD_ABSORPTION`/future `CVD_DIVERGENCE`), it will route through `post_crypto_signal_alert` and post the full crypto-aware embed (market-structure POC/CVD/book-imbalance, breakout sizing, Take/Watching/Pass buttons) to Discord for the first time in production. Not yet observed live — worth a look next time a real signal fires, rather than a synthetic proof today.

## Equity path

Not touched, not exercised today by design — equity cron (`*/15 14-21 * * 1-5`) only fires 14:00–21:59 UTC on weekdays; current time is well outside that window. Per the ruling, passive-verify is Monday RTH. Confirmed the equity log's most recent entries predate this deploy and show no errors.

## SHA / evidence trail

- Local commit at deploy time: `26f2fae` (workstreams.md DEF-NOTIFIER-STALE row opened).
- VPS backup: `/opt/openclaw/workspace/scripts/signal_notifier.py.pre-crypto-backup-20260719`.
- Hash verification: see Gate 1 table above.

**ACK — deploy done, hash-verified, new code confirmed running live via log evidence. `post_crypto_signal_alert`'s first real exercise is pending a natural new crypto signal, not yet observed — flagging honestly rather than claiming a proof I don't have.**
