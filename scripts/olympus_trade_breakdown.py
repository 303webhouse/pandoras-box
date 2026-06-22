r"""Olympus personal-trade breakdown — RH + Fidelity realized history.

Read-only. Pulls every CLOSED position (both accounts) from unified_positions,
categorizes each trade across many dimensions, and writes a committee-ready
markdown report with PnL totals, return-on-capital %, win rate, expectancy, and
profit factor per cut. Never prints the DSN.

Run from C:\trading-hub:  python scripts\olympus_trade_breakdown.py
"""
from __future__ import annotations
import json, os
from collections import defaultdict

import psycopg2

OUT = r"docs\strategy-reviews\olympus-personal-trade-breakdown-2026-06-18.md"
EXCLUDE_TICKERS = {"TEST", "TEST_C1"}  # scratch rows

# ── ticker → (sector, theme) ─────────────────────────────────────────
SECTOR = {}
THEME = {}
def reg(tickers, sector, theme):
    for t in tickers.split():
        SECTOR[t] = sector; THEME[t] = theme

reg("GDX GDXJ NUGT JNUG GDXY NEM SLV SIL GLD",          "Materials",    "Gold/Silver complex")
reg("FCX TECK",                                          "Materials",    "Base metals")
reg("CF MOS IPI MOO DBA SBU",                            "Materials",    "Ags/Fertilizer")
reg("SMH SOXS SOXL NVDA INTC SMST DRAM NBIS",            "Technology",   "Semiconductors")
reg("PLTR SOUN PATH CRCL TOST TWLO RXT IGV PANW CRWD STUB NEXT", "Technology", "Software/AI")
reg("AAPL AMZN META GOOGL NFLX TSLA TSLQ",              "Technology",   "Megacap tech")
reg("IBIT COIN BITX BITI BTCZ RIOT IREN MSTZ",          "Crypto",       "Crypto")
reg("XLE GUSH EOG HAL DINO PBR USO BOIL LNG",           "Energy",       "Oil & Gas")
reg("URA NLR",                                           "Energy",       "Uranium/Nuclear")
reg("XLF JPM GS SCHW TFC BRKB ICE SPB CRBG",            "Financials",   "Banks/Financials")
reg("PFE BMY ELV",                                       "Healthcare",   "Healthcare")
reg("WMT COST KO MO ONON EBAY UBER NOK GME PLUG XYZ",   "Consumer",     "Consumer")
reg("LUV JETS",                                          "Industrials",  "Airlines/Travel")
reg("D DUK NEE EXC",                                     "Utilities",    "Utilities")
reg("IYR WM CBRE",                                       "RealEstate",   "RealEstate/Industrials")
reg("SPY QQQ IWM RSP TQQQ SQQQ SRTY FXI QQQI",          "Broad Index",  "Index beta")
reg("TLT",                                               "Rates",        "Rates/Bonds")
reg("UVXY",                                              "Volatility",   "Volatility")

# Inverse/short ETFs: held LONG but economically BEARISH on the underlying.
INVERSE = {"SOXS","SQQQ","SRTY","TSLQ","MSTZ","BITI","BTCZ"}
# Leveraged (≥2x) ETFs (bull or bear) — for a leverage cut.
LEVERAGED = INVERSE | {"GUSH","SOXL","TQQQ","NUGT","JNUG","GDXY","BITX","BOIL","UVXY","DRAM"}


def econ_dir(asset_type, structure, direction, ticker):
    if asset_type in ("OPTION", "SPREAD"):
        return "BULLISH" if (direction or "").upper() == "LONG" else "BEARISH"
    base = "BULLISH" if (direction or "").upper() == "LONG" else "BEARISH"
    if ticker in INVERSE:  # long an inverse ETF = bearish bet
        base = "BEARISH" if base == "BULLISH" else "BULLISH"
    return base

def sec_type(asset_type, structure):
    s = (structure or "").lower()
    if asset_type == "EQUITY": return "Stock/ETF"
    if "debit_spread" in s:    return "Vertical debit spread"
    if s in ("long_call","long_put"): return "Single-leg option"
    return "Other option"

def hold_bucket(days):
    if days is None: return "unknown"
    if days <= 0:  return "0 — intraday"
    if days <= 2:  return "1-2d"
    if days <= 5:  return "3-5d"
    if days <= 15: return "6-15d"
    return "16d+"

def is_olympus(notes):
    n = (notes or "").lower()
    return any(k in n for k in ("committee","olympus","approved","scout ignore",
                                "went against","toro","ursa","pythia","pivot"))

def against_committee(notes):
    return "went against" in (notes or "").lower()


def fetch():
    cfg = json.load(open(r"C:\trading-hub\.mcp.json"))
    url = next((a for a in reversed(cfg["mcpServers"]["postgres"]["args"]) if a.startswith("postgres")), None)
    conn = psycopg2.connect(url); cur = conn.cursor()
    cur.execute("""
        SELECT account, ticker, asset_type, structure, direction,
               realized_pnl, cost_basis, entry_date, exit_date, notes
        FROM unified_positions
        WHERE status='CLOSED' AND realized_pnl IS NOT NULL
        ORDER BY exit_date
    """)
    rows = cur.fetchall()
    cur.execute("""SELECT account, ticker, asset_type, structure, direction, quantity, cost_basis
                   FROM unified_positions WHERE status='OPEN'""")
    opens = cur.fetchall()
    cur.close(); conn.close()
    return rows, opens


def main():
    rows, opens = fetch()
    trades = []
    for (acct, tk, at, st, dr, pnl, cb, ed, xd, notes) in rows:
        if tk in EXCLUDE_TICKERS: continue
        pnl = float(pnl)
        cb = float(cb) if cb is not None else None
        days = (xd.date() - ed.date()).days if (ed and xd) else None
        trades.append(dict(
            acct=acct, tk=tk, at=at, st=st, dr=dr, pnl=pnl, cb=cb, days=days,
            month=(xd.strftime("%Y-%m") if xd else "unknown"),
            sector=SECTOR.get(tk, "Other/Unmapped"),
            theme=THEME.get(tk, "Other/Unmapped"),
            sec_type=sec_type(at, st),
            econ=econ_dir(at, st, dr, tk),
            hold=hold_bucket(days),
            leveraged=("Leveraged/Inverse ETF" if tk in LEVERAGED else "Standard"),
            olympus=is_olympus(notes),
            against=against_committee(notes),
            notes=notes or "",
        ))

    unmapped = sorted({t["tk"] for t in trades if t["sector"] == "Other/Unmapped"})

    def agg(key):
        d = defaultdict(lambda: dict(n=0, pnl=0.0, wins=0, losses=0, gw=0.0, gl=0.0, cb=0.0))
        for t in trades:
            g = d[key(t)]
            g["n"] += 1; g["pnl"] += t["pnl"]
            if t["pnl"] >= 0: g["wins"] += 1; g["gw"] += t["pnl"]
            else: g["losses"] += 1; g["gl"] += -t["pnl"]
            if t["cb"]: g["cb"] += t["cb"]
        return d

    def fmt_table(d, label, sort_by_pnl=True):
        items = sorted(d.items(), key=(lambda kv: -kv[1]["pnl"]) if sort_by_pnl else (lambda kv: str(kv[0])))
        out = [f"\n### By {label}\n",
               "| "+label+" | Trades | Net P&L | Win% | Avg/trade | Profit factor | Ret on $ |",
               "|---|--:|--:|--:|--:|--:|--:|"]
        for k, g in items:
            wr = 100*g["wins"]/g["n"] if g["n"] else 0
            avg = g["pnl"]/g["n"] if g["n"] else 0
            pf = (g["gw"]/g["gl"]) if g["gl"] > 0 else float("inf")
            roc = (100*g["pnl"]/g["cb"]) if g["cb"] > 0 else None
            pf_s = "∞" if pf == float("inf") else f"{pf:.2f}"
            roc_s = f"{roc:+.1f}%" if roc is not None else "—"
            out.append(f"| {k} | {g['n']} | ${g['pnl']:+,.0f} | {wr:.0f}% | ${avg:+,.1f} | {pf_s} | {roc_s} |")
        return "\n".join(out)

    # overall
    N = len(trades); tot = sum(t["pnl"] for t in trades)
    wins = [t for t in trades if t["pnl"] >= 0]; losses = [t for t in trades if t["pnl"] < 0]
    gw = sum(t["pnl"] for t in wins); gl = -sum(t["pnl"] for t in losses)
    totcb = sum(t["cb"] for t in trades if t["cb"])
    best = sorted(trades, key=lambda t: -t["pnl"])[:8]
    worst = sorted(trades, key=lambda t: t["pnl"])[:8]

    L = []
    L.append("# Olympus Personal-Trade Breakdown — RH + Fidelity (Roth/403b)")
    L.append("\n_Realized closed trades from `unified_positions`. Read-only snapshot 2026-06-18. "
             "Directional cuts use ECONOMIC direction (inverse ETFs like SOXS/SQQQ counted BEARISH; "
             "option structure sign honored). Return-on-$ = realized P&L / cost basis where basis is recorded._\n")
    L.append("## Headline")
    L.append(f"- **{N} closed trades · net realized ${tot:+,.2f}**")
    L.append(f"- Win rate **{100*len(wins)/N:.0f}%** ({len(wins)}W / {len(losses)}L) · "
             f"profit factor **{gw/gl:.2f}** · avg trade **${tot/N:+,.2f}**")
    L.append(f"- Gross wins ${gw:,.0f} vs gross losses ${gl:,.0f}")
    if totcb: L.append(f"- Aggregate return on deployed capital (where basis recorded): **{100*tot/totcb:+.1f}%** on ${totcb:,.0f}")
    L.append(f"- Avg winner ${gw/max(len(wins),1):,.1f} · avg loser ${-gl/max(len(losses),1):,.1f} · "
             f"win/loss ratio {(gw/max(len(wins),1))/(gl/max(len(losses),1)):.2f}")

    L.append(fmt_table(agg(lambda t: t["acct"]), "Account"))
    L.append(fmt_table(agg(lambda t: t["sector"]), "Sector"))
    L.append(fmt_table(agg(lambda t: t["theme"]), "Market theme"))
    L.append(fmt_table(agg(lambda t: t["sec_type"]), "Security type"))
    L.append(fmt_table(agg(lambda t: t["econ"]), "Direction (economic, bullish vs bearish)"))
    L.append(fmt_table(agg(lambda t: t["leveraged"]), "Leverage"))
    L.append(fmt_table(agg(lambda t: t["hold"]), "Holding period / timeframe"))
    L.append(fmt_table(agg(lambda t: t["month"]), "Month", sort_by_pnl=False))
    L.append(fmt_table(agg(lambda t: ("Olympus-reviewed" if t["olympus"] else "Self-directed")), "Olympus review"))

    # Olympus-reviewed detail
    orev = [t for t in trades if t["olympus"]]
    L.append("\n### Olympus-reviewed trades (detail)\n")
    L.append("| Ticker | Acct | Type | Dir | P&L | Note |\n|---|---|---|---|--:|---|")
    for t in sorted(orev, key=lambda t: -t["pnl"]):
        L.append(f"| {t['tk']} | {t['acct'][:4]} | {t['sec_type']} | {t['econ'][:4]} | ${t['pnl']:+,.0f} | {t['notes'][:80]} |")
    if orev:
        op = sum(t['pnl'] for t in orev); ow = sum(1 for t in orev if t['pnl']>=0)
        L.append(f"\n_Olympus-reviewed: {len(orev)} trades, net ${op:+,.0f}, win {100*ow/len(orev):.0f}%. "
                 f"(Self-selected sample — not a controlled test.)_")

    # cross-cut: direction x theme (edge hunting)
    L.append(fmt_table(agg(lambda t: f"{t['theme']} · {t['econ'][:4]}"), "Theme × direction (edge hunt)"))

    L.append("\n### Best 8 trades\n| Ticker | Acct | Type | P&L | Days |\n|---|---|---|--:|--:|")
    for t in best: L.append(f"| {t['tk']} | {t['acct'][:4]} | {t['sec_type']} | ${t['pnl']:+,.0f} | {t['days']} |")
    L.append("\n### Worst 8 trades\n| Ticker | Acct | Type | P&L | Days |\n|---|---|---|--:|--:|")
    for t in worst: L.append(f"| {t['tk']} | {t['acct'][:4]} | {t['sec_type']} | ${t['pnl']:+,.0f} | {t['days']} |")

    # open exposure
    L.append("\n### Current open exposure (context, not realized)\n| Acct | Ticker | Type | Dir | Qty | Cost basis |\n|---|---|---|---|--:|--:|")
    for (acct, tk, at, st, dr, q, cb) in opens:
        e = econ_dir(at, st, dr, tk)
        cb_s = f"${float(cb):,.0f}" if cb is not None else "—"
        L.append(f"| {acct[:4]} | {tk} | {sec_type(at,st)} | {e[:4]} | {q} | {cb_s} |")

    if unmapped:
        L.append(f"\n> **Unmapped tickers (defaulted to Other):** {', '.join(unmapped)} — refine the map if any matter.")

    report = "\n".join(L) + "\n"
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f: f.write(report)

    # stdout summary
    print(f"WROTE {OUT}  ({N} trades, net ${tot:+,.0f})")
    print(f"unmapped: {unmapped}")
    print("\n=== headline cuts ===")
    for label, key in [("ACCOUNT", lambda t:t['acct']), ("SECTOR", lambda t:t['sector']),
                       ("DIRECTION", lambda t:t['econ']), ("SEC TYPE", lambda t:t['sec_type']),
                       ("TIMEFRAME", lambda t:t['hold']), ("MONTH", lambda t:t['month'])]:
        d = agg(key); print(f"\n[{label}]")
        for k,g in sorted(d.items(), key=lambda kv:-kv[1]['pnl']):
            wr=100*g['wins']/g['n']; print(f"  {str(k):<26} n={g['n']:<3} pnl=${g['pnl']:+8,.0f}  win={wr:3.0f}%")

if __name__ == "__main__":
    main()
