#!/usr/bin/env python3
"""Strip base64 image data from OpenClaw sessions."""
import json, os, glob
DIR = "/home/openclaw/.openclaw/agents/main/sessions/"
PH = "[image stripped to save context]"
def strip(c):
    if not isinstance(c, list): return c, False
    ch = False; out = []
    for b in c:
        if not isinstance(b, dict): out.append(b); continue
        if b.get("type") in ("image","image_url"):
            out.append({"type":"text","text":PH}); ch=True; continue
        t = b.get("text","")
        if isinstance(t,str) and len(t)>20000 and "media attached" in t[:200]:
            out.append({"type":"text","text":t[:200]+"\n"+PH}); ch=True; continue
        out.append(b)
    return out, ch
def process(fp):
    lines=open(fp).readlines(); orig=sum(len(l) for l in lines)
    nl=[]; cnt=0
    for line in lines:
        try: e=json.loads(line)
        except: nl.append(line); continue
        if e.get("type")=="message":
            m=e.get("message",{}); c=m.get("content")
            if c:
                nc,ch=strip(c)
                if ch: m["content"]=nc;e["message"]=m;cnt+=1
        nl.append(json.dumps(e)+"\n")
    if cnt>0:
        open(fp,"w").writelines(nl)
        print(f"  {cnt} imgs, {orig-sum(len(l) for l in nl):,}B saved")
    return cnt
def main():
    t=0
    for fp in glob.glob(os.path.join(DIR,"*.jsonl")):
        if "reset" in fp or "bak" in fp: continue
        if os.path.getsize(fp)<50000: continue
        print(f"Processing {os.path.basename(fp)}...")
        t+=process(fp)
    print(f"\nTotal stripped: {t}")
if __name__=="__main__": main()
