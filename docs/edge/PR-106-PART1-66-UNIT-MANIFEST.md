# PR-106 PART-1 — THE 66 CONTRIBUTING UNITS · ID MANIFEST

**FRESH DERIVATION, GATE-VERIFIED.** Not a recovery: no filed original ever existed,
which is why this files now. Derived by CC-QUERY per EDGE's R-IV.174 criterion,
verified against the filed render before publication.

## Gate results — both mandatory checks PASS

| gate | expected | observed | |
|---|---|---|---|
| per-cell counts | `[14, 7, 9, 12, 24]` | `[14, 7, 9, 12, 24]` | **PASS** |
| distinct tickers | the published 25, set-identical | 25, set-identical | **PASS** |
| unit count | 66 | 66 | **PASS** |

## Sources — TWO, and only one is a file

The 66 is **not derivable from `merged_ledger.csv` alone.** That file is Fidelity-only
by content and yields **50 units / 20 tickers** — which is correct for the file. The
remaining 16 units and 5 tickers come from a Robinhood DB read.

**SOURCE A — file, hash-pinned**
```
path   data/imports/90d/merged_ledger.csv
bytes  11418
sha256 6ab4d5c1f9c2315281349432e004718816844c3d6885c9eca159c24bb800f9d6
mtime  2026-08-26 21:04:10Z  (15:04:10 local)
yields 50 units / 20 tickers after smoke and cell-only exclusions
```

**SOURCE B — DB read, WALL-TIME-pinned, NOT hash-pinned**
```
origin    unified/positions read, Robinhood half, 18 rows
WALLTIME  2026-08-27 17:38:08.570701
yields    16 units / 5 new tickers (CF, CRCL, ICE, IPI, NBIS) after smoke exclusion
```

> **PROVENANCE ASYMMETRY, stated rather than smoothed:** 50 of the 66 units trace to a
> hashed file and can be re-derived byte-exactly. **16 trace to a database read pinned
> only by wall-time** — re-running that read today may not reproduce the same rows, and
> no hash exists to detect it if it does not. Those 16 are marked `src=B` below. Any
> consumer needing byte-reproducibility has it for 50 units and does not have it for 16.

## Criterion applied

ADMITTED disposition · equity/ETF · both accounts · MINUS smoke (TEST 171, TEST_C1 172)
· MINUS cell-excluded/population-retained (SBU, SSPC, WRTH). Nothing re-subtracted from
the upstream-excluded dispositions (LIFECYCLE-UNVALIDATED 11 · OVERLAP-UNMATCHED 10 ·
SUPERSEDED-BY-EXPORT 8 · UNKNOWN-BASIS 5 · STILL-OPEN 2 · INVALID-LIFETIME 3).

## The 66 units

`src` A = merged_ledger.csv · B = Robinhood DB read.

| # | cell | ticker | src | unit id |
|---|---|---|---|---|
| 1 | SEMIS/DRAM | RAMZ | A | `bcf74fdc94bc167a;c80de60ebaa0b70f;00e35ffcc0712cf7` |
| 2 | SEMIS/DRAM | SOXL | A | `POS_SOXL_20260413_185918` |
| 3 | SEMIS/DRAM | SOXS | A | `114cc0d932c588b4;5036cc05f71fc04b;b2bc846da228d690;8de85c8b496f7f52;f7e7ea4a0360440a;4dc0765e9f0b120f` |
| 4 | SEMIS/DRAM | SOXS | B | `188` |
| 5 | SEMIS/DRAM | SOXS | B | `348` |
| 6 | SEMIS/DRAM | SOXS | B | `354` |
| 7 | SEMIS/DRAM | SOXS | B | `382` |
| 8 | SEMIS/DRAM | SOXS | B | `383` |
| 9 | SEMIS/DRAM | SOXS | A | `3c1b9e7b4caa1b68;c14bb74794ec69cc;3ead109640ee767c;1e91a06b013ef543` |
| 10 | SEMIS/DRAM | SOXS | A | `5ebd6b70890cc732;e671f12c493bbe77;b436b5dd9ad85d13;cc466c7ba2e384ec;0b5bc0e572185648;d629526bb80b9bb2;2843da23a70d524b` |
| 11 | SEMIS/DRAM | SOXS | A | `76cfcda5a8b09588;c1c1504ec93374ae;9e216223fc4c392c;8c032f013d8ff134;1d663b2865d3adca;5b53f68a6ce3a2b4;67a3f69959779b9d;d1fd83adb778f6f8;36a9542889b93296;54ab1736b0d42130;2d59c5c327aa3f6a;10eabdfb196916b4;ad266b3f63880e0a` |
| 12 | SEMIS/DRAM | SOXS | A | `8f3e2ab04e811965;e2fd1a6a2e9d6508` |
| 13 | SEMIS/DRAM | SOXS | A | `b0279536405419cb;e6b303baa8263a10;72c442adda098067;4a3cd1c742773c9b;15a0ff264152fdf2;e824fb871e00139c` |
| 14 | SEMIS/DRAM | SOXS | A | `cf5e1fefd4cbbefb;9db1a9b8ac3a8efc` |
| 15 | ENERGY | GUSH | A | `19e14713c32ee166;eba6a2aca82ac474;58e8d7e2ceebf5e3;be51531949c959e4;dc1ffc7bfeddc7ae;d9bfc2bc7fef73ba;c9597a9a8db75745;485752cfc94dac0a;05cd8acbdfbcca4f;951204652614c69b;b9a85eadeb5c3f98;542bc6f60f747f5b;7bdeee809f48f097;25a303a533c4f664;8985ebd5428b5be3` |
| 16 | ENERGY | GUSH | B | `358` |
| 17 | ENERGY | GUSH | A | `8d7d531e2a8bc0c3;184b42b79709dc4e` |
| 18 | ENERGY | GUSH | A | `ac06073cfae406d7;4c40c3fc11a71f00;34654af2027c0fbe;403aa0929d8b60ec` |
| 19 | ENERGY | GUSH | A | `f65e40e4a1d169ba;ffb695b201cac67e` |
| 20 | ENERGY | NLR | A | `12eab9868ad084b2;63d0ad7ccb7f792b` |
| 21 | ENERGY | URA | A | `POS_URA_20260526_170738` |
| 22 | PRECIOUS METALS/MINERS | GDX | A | `POS_GDX_20260413_185751` |
| 23 | PRECIOUS METALS/MINERS | GDX | A | `POS_GDX_20260526_170241` |
| 24 | PRECIOUS METALS/MINERS | GDXJ | A | `130ca49b813bcb18;30bc4f513386571b;a0bdd65dec7d60e0` |
| 25 | PRECIOUS METALS/MINERS | GDXJ | A | `4b03b0e7b8e42380;70a7975c103c7398;ebd73bab641dfd63;e2b4f9f2c877f630` |
| 26 | PRECIOUS METALS/MINERS | GDXJ | A | `5d4a08ff85fd1af4;d6f2b149ebaea2fc` |
| 27 | PRECIOUS METALS/MINERS | GDXJ | A | `e5c9f2313c6ae9ab;b52f4a522fc07ade;d3ce596ee7689c73` |
| 28 | PRECIOUS METALS/MINERS | GDXJ | A | `ed5b00a9163235fc;ebc45895e7cf8c0c` |
| 29 | PRECIOUS METALS/MINERS | JNUG | A | `9f8cb2cf7ce493b6;2a6f6f0cdb8d0522` |
| 30 | PRECIOUS METALS/MINERS | NUGT | A | `0ce4ba9f543adf56;301257d148cc89de` |
| 31 | CRYPTO | BITI | A | `POS_BITI_20260526_180554` |
| 32 | CRYPTO | BITX | A | `190d1e2072b89164;3fa5103502e0ce84` |
| 33 | CRYPTO | BITX | A | `41b832b9500f669d;239fc97c42725d30` |
| 34 | CRYPTO | BITX | A | `464dc2f821fbddc8;d2234c33b22b94d2;2c268e0c509429b8` |
| 35 | CRYPTO | BITX | A | `e311363dc091e5f3;080b0c6d5c5ddd59` |
| 36 | CRYPTO | BTCZ | A | `POS_BTCZ_20260319_173043` |
| 37 | CRYPTO | CRCL | B | `71` |
| 38 | CRYPTO | CRCL | B | `82` |
| 39 | CRYPTO | CRCL | B | `89` |
| 40 | CRYPTO | MSTZ | A | `7ae0b97181feb1a7;10255eb4f5058408` |
| 41 | CRYPTO | MSTZ | A | `84e38da8dcfe2f08;8819c18c8d766a0c` |
| 42 | CRYPTO | MSTZ | A | `e91f51906181acff;f0227068936e0902` |
| 43 | OTHER | CF | B | `151` |
| 44 | OTHER | ICE | B | `92` |
| 45 | OTHER | IPI | B | `152` |
| 46 | OTHER | IPI | B | `153` |
| 47 | OTHER | IPI | B | `181` |
| 48 | OTHER | MOO | A | `15c15567393dfc48;c8498129e4f451ee` |
| 49 | OTHER | MOO | A | `79e526b0eeb3b7b5;fded41bc00524779;96ed4c2656b77aee` |
| 50 | OTHER | MOO | A | `POS_MOO_20260423_191028` |
| 51 | OTHER | MOO | A | `POS_MOO_20260513_175350` |
| 52 | OTHER | NBIS | B | `91` |
| 53 | OTHER | QQQI | A | `POS_QQQI_20260413_185841` |
| 54 | OTHER | SQQQ | A | `441d9025960da93f;c27d8cf622ba8b23` |
| 55 | OTHER | SQQQ | A | `POS_SQQQ_20260318_051303` |
| 56 | OTHER | SQQQ | A | `POS_SQQQ_20260401_174055` |
| 57 | OTHER | SQQQ | A | `POS_SQQQ_20260407_165301` |
| 58 | OTHER | SQQQ | A | `c2dff78d7c3e9a7c;69f5a7b71481b681;f1ebf50db1f085c8` |
| 59 | OTHER | SQQQ | A | `e31728f4179ace30;f1184b76255546c5;ee0a77dd2aec089c;7da88cf877640db3` |
| 60 | OTHER | SRTY | A | `POS_SRTY_20260423_184258` |
| 61 | OTHER | TLT | A | `POS_TLT_20260311_183448` |
| 62 | OTHER | TSLQ | A | `2eff5d14c095ccab;8896d9dd4923ce69` |
| 63 | OTHER | TSLQ | B | `69` |
| 64 | OTHER | TSLQ | A | `POS_TSLQ_20260311_183449` |
| 65 | OTHER | TSLQ | A | `POS_TSLQ_20260423_184227` |
| 66 | OTHER | TSLQ | A | `d874d49667a17d5d;f4a0471a258a54cf` |

Per-cell: SEMIS/DRAM 14 · ENERGY 7 · PRECIOUS METALS/MINERS 9 · CRYPTO 12 · OTHER 24 = 66.

Source split: A 50 · B 16.

---

## DETERMINISM PIN for src=B — and a RE-KEY FINDING that supersedes the ids above

**The `src=B` ids in the table above are STALE. `trades` has been re-keyed since the
2026-08-27 capture.** Verified 2026-09-02: every captured id now resolves to a *different*
trade — id 188 was SOXS, now PFE; 354 was SOXS, now TJX; 382 was SOXS, now IGV — and eight
captured ids (69·71·82·89·91·92·151·152) are absent from `trades` entirely.

This is **membership-identity loss, not value float.** Spine's expectation that ids 91/92
would show post-read value corrections is overtaken: those ids no longer denote those rows.

**The underlying units survive** and are recoverable by content key `(ticker, opened_at)`,
which resolves 17 of 18 captured rows. That key — not the id — is the durable identifier.

### Canonical re-derivation for src=B

```sql
SELECT id, ticker, account, opened_at, closed_at, quantity, pnl_dollars
FROM trades
WHERE (ticker, opened_at) IN ( <the 16 content keys below> )
ORDER BY id;
```

### Old-to-current id map (content-keyed, as-of 2026-09-02)

| captured id | ticker | opened_at (content key) | current id | state |
|---|---|---|---|---|
| 151 | CF | `2026-04-23 18:29:24.433458+00` | **416** | match |
| 71 | CRCL | `2026-03-11 14:57:27.951875+00` | **262** | match |
| 82 | CRCL | `2026-03-14 18:52:01.77781+00` | **360** | match |
| 89 | CRCL | `2026-03-17 18:05:29.385991+00` | **362** | match |
| 358 | GUSH | `2026-07-24 18:14:46.986925+00` | **597** | VALUE CHANGED 6.40 -> 6.15 |
| 92 | ICE | `2026-03-17 18:06:09.741096+00` | **365** | match |
| 152 | IPI | `2026-04-23 18:31:19.272765+00` | **417** | match |
| 153 | IPI | `2026-04-23 18:32:02.073057+00` | **418** | match |
| 181 | IPI | `2026-05-13 17:45:45.139538+00` | **440** | match |
| 91 | NBIS | `2026-03-17 18:05:57.374942+00` | **364** | match |
| 188 | SOXS | `2026-05-14 18:00:54.503567+00` | **446** | match |
| 348 | SOXS | `2026-07-07 06:00:00+00` | **571** | match |
| 354 | SOXS | `2026-07-15 00:00:00+00` | **587** | match |
| 382 | SOXS | `2026-08-05 13:00:10+00` | **—** | **NO MATCH** — no current row |
| 383 | SOXS | `2026-08-17 13:00:11+00` | **598** | match |
| 69 | TSLQ | `2026-03-11 00:08:48.998135+00` | **261** | VALUE CHANGED 24.10 -> 109.85 |

**Membership: 15 of 16 src=B units re-resolve. One does not** — SOXS captured id 382
(`opened_at 2026-08-05 13:00:10`, pnl 5.14) has **no current `trades` row** under any id.
Whether it was deleted, merged, or re-timestamped is not determinable from this table.

**Values: 13 match exactly; 2 changed** — GUSH 6.40 → 6.15 and TSLQ **24.10 → 109.85**.
Value movement under ruled writes is expected and is not drift. **Membership movement is
not expected, and it happened.**

*[CC-BUILD filing correction, R-IV.184(a). The Values line above was authored as “14 match exactly” and is corrected to 13. Counted mechanically off the table: 16 rows, 1 NO MATCH, 2 VALUE CHANGED, 13 plain `match`. 14 + 2 = 16 counts the NO-MATCH row as a value match, but a row with no current row cannot match a value. Against the 15 that re-resolve: 13 exact + 2 changed = 15. The slip ran in the direction that overstates stability — the direction this section exists to warn about.]*

> **CONSEQUENCE FOR ANY ID-LEVEL INTERSECTION:** a numeric id match against this manifest
> proves nothing unless both lists draw from the same keyspace. Two keyspaces now exist for
> the same rows — pre-re-key (captured) and current. State which one an id list uses before
> intersecting, or the result is a coincidence of integers.
