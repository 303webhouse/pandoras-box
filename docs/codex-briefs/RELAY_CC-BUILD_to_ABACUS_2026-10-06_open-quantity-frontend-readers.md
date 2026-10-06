# RELAY — CC-BUILD → ABACUS · the frontend readers of `quantity`, for R-IV.662

**Written for:** ABACUS, which owns the frontend readers and moves them.
**Authority:** R-IV.660(b)3 ("Frontend readers are ABACUS's: list them, and ABACUS moves them").
**Date:** 2026-10-06. **Backend commit:** `d31370a`, live and healthy.

---

## What changed on the backend, in one paragraph

Convention #29 names two figures. `quantity` is the size the position was **OPENED** at, adds
included — it does **not** shrink when part of the position is closed, because the cost basis and
every percentage over it belong to the trade as taken. What is still held is the **open
remainder**, the sum of the position's lot quantities.

Until today the payload served only the first, so anything asking "how big is this position right
now" got the opened size. That was right by accident while a partial close shrank the column;
R-IV.657(c) correctly stopped the shrinking, which made the overstatement live.

**Every position payload now carries `open_quantity` and `open_quantity_basis`.** Nothing needs
to compute it, and nothing should read `quantity` for it.

```
quantity              the size opened, adds included        (unchanged meaning, now unshrinking)
open_quantity         what is STILL OPEN                    (new — read this for live size)
open_quantity_basis   where that figure came from           (new — read before trusting it)
```

`open_quantity_basis` is `"lots"` when measured. **A null `open_quantity` means the remainder is
UNKNOWN** (the position has no lots) — that is *not* zero and must not render as a flat position.
Today no open row is in that state (28 of 28 have lots, measured 2026-10-06), so this is a guard,
not a common case.

Surfaces now serving both fields: `GET /api/v2/positions`, `/v2/positions/summary`,
`/v2/positions/{id}`, the legacy `GET /api/positions`, the River's touches blocks, and
`hub_get_positions`.

**One exception worth knowing:** on the legacy `GET /api/positions` shape, `quantity` now carries
the **open remainder** and the opened size moved to `quantity_opened`. That route's consumers have
always meant "live size" by that field, so changing the value was less disruptive than changing
every reader. `open_quantity` is served there too and is identical to `quantity`. On the v2 routes
`quantity` keeps its #29 meaning — the two routes differ deliberately, and the field names say so.

---

## The readers, by file

Split by what each one would get wrong. The only rows where the two figures currently differ is
`POS_HYG_20260922_203634_L2` (HYG: opened 5, closed 2, holds 3) — so a mistake here is visible on
exactly one position today and on every partial close from now on.

### `frontend/v2.js` — Agora, the live page

| line | code | what it is | why it matters |
|---|---|---|---|
| 1680 | `'×' + p.quantity + ' sh'` | stock row size label | shows the opened size as the holding |
| 1685 | `' ×' + p.quantity` | option row size label | same |
| 1791 | `kv('Qty', p.quantity)` | detail panel | same |
| 2003 | `value="${p.quantity != null ? p.quantity : 1}"` | **close form default** | pre-fills a close with the opened size, so "close all" asks for 5 where 3 are held |
| 2015 | `parseInt(...) \|\| p.quantity \|\| 1` | close submit fallback | same, on the fallback path |

**2003 and 2015 are the two that matter most.** The backend now clamps a close to the remainder
and decides partial-vs-full against it, so an over-sized request cannot corrupt the book — but
the dialog would still *tell the principal* he holds 5 when he holds 3, and he would approve it.

### `frontend/app.js` — legacy

| line | code | what it is |
|---|---|---|
| 2552 | `<td>${pos.quantity}</td>` | table cell |
| 5005 | `Qty: ${p.quantity \|\| '--'}` | summary line |
| 10201 | `${pos.quantity \|\| '--'}` | position detail |
| 10336–10341 | `(currentPrice - position.entry_price) * position.quantity` | **P&L, computed in the page** |
| 10372 | `closeQuantity.value = position.quantity` | close form default |
| 10374 | `` `You have ${position.quantity} ${unitLabel}` `` | **"You have N" hint — states the wrong holding** |
| 10500 | `if (closeQty > closingPosition.quantity)` | close validation bound |
| 10658 | `if (position && closeQty >= position.quantity)` | full-close detection |
| 10833 | `const maxLoss = entryPrice * quantity` | **risk figure** |
| 10842–10843, 10850 | `premium * 100 * quantity`, `(width - premium) * 100 * quantity` | **max loss / max profit** |

**`app.js` has TWO position-list sources, and which one feeds a given reader decides whether it
needs touching at all:**

| fetch | route | what `quantity` means there |
|---|---|---|
| `app.js:2507` | `/api/portfolio/positions` (legacy) | the **open remainder** — already correct |
| `app.js:9421` | `/v2/positions?status=OPEN` | the **size opened** — needs moving |

I am **not** giving you a per-reader mapping, because I cannot establish one honestly from here:
lexical proximity to a fetch is not data flow, and the rows above travel through render helpers I
would be guessing about. The two sources and the ten readers are the facts; tracing which feeds
which is a read you are better placed to do than I am. If any reader turns out to be fed by
`/api/portfolio/positions`, it is already right and should be left alone.

### Legitimately reads the opened size — do NOT change

| line | code | why |
|---|---|---|
| `app.js` 11002 | `const curQty = position.quantity \|\| 0` | the EDIT form, which edits the size opened |
| `app.js` 11014 | `editQuantity.value = position.quantity` | same |
| `app.js` 11053, 11064 | `updates.quantity = ...` | writes the size opened, correctly |

### Not this field at all

`app.js` 11947, 12027 and `laboratory.js` 446 read `leg.quantity` — a **leg's** own quantity, a
different column on `position_legs`. Out of scope.

---

## How to tell you are done

A position with a partial close shows the **held** size everywhere it shows a size, and the
**opened** size only in the edit form. The live case to look at is HYG
`POS_HYG_20260922_203634_L2`: it should read 3, and its close dialog should offer 3.

One caveat on that row, so it does not confuse you: its **stored** `quantity` is still 3, because
it was reduced by the unfixed `/reduce` before today's fix. Under #29 it should be 5. I have
deliberately **not** corrected the data yet — while the page still reads `quantity` as live size,
the wrong stored value is accidentally protective, and correcting it first would overstate a real
position on screen. **Tell me when your readers are moved and I will correct the row**, which is
when `quantity 5 / open_quantity 3` starts appearing and is the real end-to-end test.

Anything unclear, ask — the backend fields are settled and I would rather answer than have a
reader guess which figure it is holding.

---

## One thing that does NOT affect you, checked so you do not have to

`/v2/positions/summary` now **refuses** a bare `?account=FIDELITY` with a 400 naming both Fidelity
keys and both account numbers — two of the three accounts are Fidelity BrokerageLink accounts and
no name tells them apart (R-IV.638(b)3, applied here by R-IV.660(c)1). I grepped the frontend for
a bare `account=FIDELITY` before shipping it: **there is none.** `app.js:9442-9443` already ask for
`ROBINHOOD` and `FIDELITY_ROTH` by key, so nothing on the page breaks.

Related, and visible to the principal immediately: the **401(a) is now in scope for money**. The
balances headline reads **24,786.57 across "3 of 3 accounts"** where it read 12,881.24 across 2 of
3, because `is_in_scope` had been answering by capitalisation and the balances tool lowercases its
account key. If any ABACUS surface carried a hardcoded "2 of 3" or its own tracked-account list,
that is now wrong and worth a look.
