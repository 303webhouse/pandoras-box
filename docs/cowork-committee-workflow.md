# Cowork Committee Deep Review Workflow

## Purpose
When the VPS bridge posts a streamlined committee review to Discord, Cowork runs
a deeper analysis using tools the VPS doesn't have: web search, vision, Claude in
Chrome for UW flow, and conversational follow-up.

## Trigger
Run this workflow every 5 minutes during market hours (9:30 AM - 4:00 PM ET),
or on demand when Nick asks for a deep review.

## Steps

### 1. Check for new committee reviews
Query the Railway API for reviews posted since last check:
```
curl -sH "X-API-Key: rLl-7i2GqGjie5in9iHIlVtqlP5zpY7D5E6-8tzlNSk" \
  "https://pandoras-box-production.up.railway.app/api/committee/history?limit=5"
```
If no new reviews since last check, stop.

### 2. For each new review, run deep analysis
For each ticker in the new reviews:

a. **Web search** for breaking news on the ticker (last 4 hours)
b. **Web search** for Trump/political headlines that could affect the trade
c. **Verify current price** via web search
d. **Check open positions** in `C:\trading-hub\docs\open-positions.md` — does this
   signal conflict with or complement existing positions?
e. **Check the "what invalidates" column** for any related positions
f. **Anti-confirmation bias check**: Does this signal reinforce Nick's existing
   thesis? If so, actively look for counter-evidence.
g. **Check macro-economic-data.md** for relevant data points

### 3. Write deep review to local file
Save to `C:\trading-hub\committee-reviews\<TICKER>-<YYYY-MM-DD>.md` with:
- VPS committee summary (action, conviction, synthesis)
- Deep analysis findings (news, price, position conflicts)
- Anti-bias assessment
- Final recommendation: agree with VPS committee, disagree, or flag for Nick

### 4. Post notification to Discord
```
curl -X POST "https://discordapp.com/api/webhooks/1493053445291376824/Iuecb5TVpOMOxU2M72RtkJwzvx6poLckKSpBw75lfCmq-bLLlVZLNwpeocMAEkbAuFVB" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "Cowork Deep Review",
    "content": "Deep review complete for **<TICKER>**",
    "embeds": [{
      "title": "<TICKER> -- <ACTION> -- <CONVICTION>",
      "description": "<2-3 sentence summary of deep findings>",
      "color": 3066993,
      "fields": [
        {"name": "VPS Committee", "value": "<TAKE/PASS/WATCHING>", "inline": true},
        {"name": "Deep Review", "value": "<AGREE/DISAGREE/FLAG>", "inline": true},
        {"name": "News Check", "value": "<any breaking news found>", "inline": false}
      ]
    }]
  }'
```

### 5. Update tracking
Note the timestamp of the last review processed to avoid re-processing.
