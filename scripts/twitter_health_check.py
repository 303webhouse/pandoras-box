"""Twitter scraper health check. Runs daily via cron."""
import json, os, pathlib, subprocess
from datetime import datetime, timezone

# Load token from environment — never hardcode
def _load_token():
    tok = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if tok:
        return tok
    cfg_path = pathlib.Path("/home/openclaw/.openclaw/openclaw.json")
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        return (((cfg.get("channels") or {}).get("discord") or {}).get("token") or "").strip()
    except Exception:
        return ""

TOKEN = _load_token()
CHAN = "1474135100521451813"
SIG = pathlib.Path("/opt/openclaw/workspace/data/twitter_signals.jsonl")

def send(msg):
    d = json.dumps({"content": msg})
    subprocess.run(["curl", "-s", "-X", "POST",
        f"https://discord.com/api/v10/channels/{CHAN}/messages",
        "-H", f"Authorization: Bot {TOKEN}",
        "-H", "Content-Type: application/json",
        "-d", d], capture_output=True, timeout=15)

last = None
if SIG.exists():
    for l in SIG.open():
        l = l.strip()
        if l:
            try: last = json.loads(l).get("timestamp", "")
            except: pass
if not last:
    send("\u26a0\ufe0f **Twitter Scraper Down** \u2014 No signal data found.")
    print("ALERT: no data")
else:
    t = datetime.fromisoformat(last.replace("Z", "+00:00"))
    h = int((datetime.now(timezone.utc) - t).total_seconds() / 3600)
    if h > 24:
        send(f"\u26a0\ufe0f **Twitter Scraper Down** \u2014 Last signal was {h}h ago.\nAuth tokens expired. To fix:\n1. Log into X in browser\n2. DevTools > Application > Cookies\n3. Copy auth_token + ct0\n4. `crontab -u openclaw -e` and update both values")
        print(f"ALERT: {h}h stale")
    else:
        print(f"OK: {h}h ago")
