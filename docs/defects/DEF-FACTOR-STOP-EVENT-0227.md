# DEF-FACTOR-STOP-EVENT-0227 · P2

**Registered** 2026-09-09 by R-IV.331(e). **Status:** OPEN — registration only.
**Investigation HELD.** **Cause UNREAD.**

---

## The observation

**Nine factors stopped between 2026-02-27 and 2026-03-04, in one cluster.**

**That is the whole of it.** Spine's datum, registered so the cluster has a name before
anyone re-derives it.

## Why it is registered rather than investigated

**A nine-factor cluster inside a six-day window is not nine independent failures.** Nine
things stopping together have one cause far more often than nine, and **the shape of the
cluster is itself the evidence** — which is why it is worth naming now and worth reading
carefully later, rather than quickly.

**It is P2 and not higher because nothing sizes off those nine today**, and it is P2 rather
than P3 because a common-cause stop that has never been diagnosed **can recur without being
recognised as a recurrence.**

## What this file deliberately does NOT contain

**No mechanism, no candidate list, no ticker or factor names beyond the count.** This lane
has spent two days correcting attributions made from partial reads (`conventions #14`), and **a stop
cluster is exactly the shape that invites a plausible story.**

**The discriminator that applies when it is read** — conventions #14 — is: for each of the
nine, **did the raw input stop, or did the score stop?** Those are different events with
different causes, and **the answer is in the raw payload, not in the scores.**

## What would open it

- The nine names and their exact last-write timestamps.
- Whether they share a writer, a source, or a schedule.
- Whether `factor_readings` shows raw arriving after the score stopped for any of them — which
  would separate a collection failure from a scoring failure in one query.
