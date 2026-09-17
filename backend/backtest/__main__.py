"""CLI.  cd backend && python -m backtest <command>

  known-answers                      acceptance #2, live (network only; no database)
  history --symbol SPY --start 2020-01-01 [--max-hold 10]
                                     CIRCE'S STEW, vanilla, over history (network only)
  grade --population three_ten       one grading pass (DATABASE -- run where the app runs)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import date


def _known_answers(_args) -> int:
    from . import known_answers
    results = known_answers.run()
    print(json.dumps(results, indent=2, default=str))
    verdicts = [r.get("pass") for r in results]
    print(f"\nPASS {sum(v is True for v in verdicts)} | FAIL {sum(v is False for v in verdicts)}"
          f" | UNAVAILABLE {sum(v is None for v in verdicts)} | of {len(verdicts)}")
    return 0 if all(v is True for v in verdicts) else 1


def _history(args) -> int:
    from . import bars, engine, metrics
    end = date.today()
    s = bars.fetch_daily([args.symbol], date.fromisoformat(args.start), end).get(args.symbol.upper())
    if s is None:
        print("no bars returned")
        return 1
    grades = engine.run_history(s, engine.circe_triggers, engine.circe_lookback(),
                                args.max_hold, "circes_stew")
    rows = [g.as_dict() for g in grades if g.status == "graded"]
    summary = metrics.summarize_r(rows, sessions=s.dates)
    print(json.dumps({"strategy": "circes_stew (VANILLA: no location gate, no regime)",
                      "symbol": args.symbol.upper(), "first_bar": s.dates[0], "last_bar": s.last,
                      "basis": s.basis(), "max_hold": args.max_hold,
                      "triggers": len(grades), "graded": len(rows), "summary": summary},
                     indent=2, default=str))
    return 0


def _grade(args) -> int:
    from database.postgres_client import get_postgres_client
    from . import job, sessions
    from .populations import POPULATIONS

    async def go():
        pool = await get_postgres_client()
        async with pool.acquire() as conn:
            return await job.grade_population(conn, POPULATIONS[args.population],
                                              sessions.complete_through())
    print(json.dumps(asyncio.run(go()), indent=2, default=str))
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="python -m backtest")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("known-answers")
    h = sub.add_parser("history")
    h.add_argument("--symbol", required=True)
    h.add_argument("--start", required=True)
    h.add_argument("--max-hold", type=int, default=10)
    g = sub.add_parser("grade")
    g.add_argument("--population", required=True, choices=["three_ten", "pass9", "circes_stew"])
    args = p.parse_args(argv)
    return {"known-answers": _known_answers, "history": _history, "grade": _grade}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
