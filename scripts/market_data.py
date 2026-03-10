#!/usr/bin/env python3
import sys,json,datetime
from zoneinfo import ZoneInfo
import yfinance as yf
D={"^VIX":"VIX","DX-Y.NYB":"DXY"}
M={"VIX":"^VIX","DXY":"DX-Y.NYB","TNX":"^TNX","10Y":"^TNX"}
DEF=["SPY","^VIX","DX-Y.NYB","QQQ","IWM"]
def q(s):
 try:
  t=yf.Ticker(s);i=t.fast_info;p=i.get("lastPrice");pc=i.get("previousClose")
  if p is None:return{"sym":D.get(s,s),"err":"no data"}
  c=p-pc if pc else 0;pct=(c/pc*100) if pc else 0
  return{"sym":D.get(s,s),"p":round(p,2),"c":round(c,2),"pct":round(pct,2),"hi":round(i.get("dayHigh",0),2),"lo":round(i.get("dayLow",0),2)}
 except Exception as e:return{"sym":s,"err":str(e)}

args=[a for a in sys.argv[1:] if a!="--json"]
tix=args if args else DEF
res=[q(M.get(t.upper(),t.upper())) for t in tix]
et=datetime.datetime.now(ZoneInfo("America/New_York"))
mt=datetime.datetime.now(ZoneInfo("America/Denver"))
if "--json" in sys.argv:
 print(json.dumps({"ts_et":str(et),"ts_mt":str(mt),"data":res},indent=2))
else:
 print("Market Data -",et.strftime("%I:%M %p ET"),"/",mt.strftime("%I:%M %p MT"))
 print("-"*55)
 for r in res:
  if "err" in r:print(f"  {r['sym']:<6} ERROR: {r['err']}")
  else:
   sg="+" if r["c"]>=0 else ""
   print(f"  {r['sym']:<6} {r['p']:>9.2f}  {sg}{r['c']:.2f} ({sg}{r['pct']:.2f}%)  L:{r['lo']:.2f} H:{r['hi']:.2f}")
