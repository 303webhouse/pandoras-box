# Vacation card — clearing an armed circuit breaker by hand

**For:** Nick, from anywhere, without a laptop and without a code change.
**Why this exists:** there is no reset button on the board. The reset endpoint exists but
nothing in the UI calls it, so if the market-risk breaker arms while you are away you need
a written path back. (DEF-KILLSWITCH-FAILOPEN, A3 gap — accepted by spine, recorded here.)

## First: is it actually armed?

Open the board on your phone and look at the **Kill-switch** cell.

| Cell reads | Meaning | Action |
|---|---|---|
| **NO TRIP ON RECORD** | healthy resting state, nothing stored | none — this is normal |
| **CLEAR** | the system confirmed no breaker is active | none |
| **ARMED** (red, pulsing) | a breaker fired — bias is capped/floored and scoring throttled | use this card |
| **ARMED · PENDING** | fired, timer elapsed, waiting for you to accept the reset | use this card |
| **UNKNOWN** (amber) | the board could not reach the source | not a clear — retry before assuming anything |

## The procedure — two steps, in this order

**Order matters. Deleting without restarting does nothing; restarting without deleting puts
the breaker straight back.** The live state lives in the app's memory. Redis only holds a
copy that is read once, at startup. So you delete the copy first, then restart so the app
comes up with nothing to restore.

### Step 1 — delete the stored breaker record

1. Open the **Upstash** console and sign in.
2. Open the Pandora Redis database → **Data Browser**.
3. Find the key **`bias:circuit_breaker`** and delete it.
   - If the key is **not there**, skip to step 2 — nothing was persisted, and the restart
     alone will clear the in-memory state.

### Step 2 — restart the backend

1. Open the **Railway** dashboard and sign in.
2. Project **fabulous-essence** → service **pandoras-box**.
3. **Restart** the service (or trigger a redeploy of the current deployment).
4. Wait ~2 minutes for it to come back.

### Step 3 — confirm it worked

Reload the board. The Kill-switch cell should now read **NO TRIP ON RECORD**.

That is the confirmation: the app restarted, found no stored record, and is telling you
truthfully that it has nothing on file. If it still reads ARMED, the record was not deleted
before the restart — repeat step 1, then step 2.

## Alternative, if you have a laptop

`POST /webhook/circuit_breaker/reset` clears it in one call, no restart needed. It accepts
**either** your normal signed-in browser session **or** the machine API key:

- **Signed in already** (browser devtools console, same tab as the board):
  ```js
  fetch('/webhook/circuit_breaker/reset', {
    method: 'POST',
    headers: { 'X-Requested-With': 'XMLHttpRequest' }   // required; CSRF defense
  }).then(r => r.json()).then(console.log)
  ```
- **With the API key** (any REST client): `POST` the same path with an `X-API-Key` header
  set to `PIVOT_API_KEY`. Look the value up from the environment when you need it — do not
  copy it onto a phone or into a note.

This path is cleaner than delete-and-restart because it also writes a truthful `CLEAR`
record, so the board will read **CLEAR** rather than NO TRIP ON RECORD afterwards.

## Two things worth knowing

**An armed breaker no longer clears itself. This procedure is the only way out.**

It used to expire after 24 hours, and a restart a day later would come back clear on its
own. That was a safety net you had by accident, and it was the wrong kind: a safety device
that quietly disarms itself is worse than none, because the board keeps telling you it is
protecting you. DEF-KILLSWITCH-TTL-RESTART removed it — an **armed** record now persists
until someone clears it.

So the steps above are load-bearing now, not a curiosity. They are deliberately all
dashboard clicks: no console, no credentials on your phone, nothing you need a laptop for.

**A cleared record still ages out after 24 hours**, which is why the board drifts back to
NO TRIP ON RECORD a day after a reset. That is normal and correct — it means the system has
no *stored* event any more, not that anything is wrong.

## What "armed" is actually doing while you wait

It is not blocking anything you do by hand. It caps and floors the composite bias and
applies a scoring modifier — [`composite.py`](../../backend/bias_engine/composite.py) and
[`bias_scheduler.py`](../../backend/scheduler/bias_scheduler.py) read the state and
constrain signal output. Trading manually is unaffected; automated bias output is
conservative until it clears. There is no emergency here — an armed breaker left armed is
the safe direction to fail.
