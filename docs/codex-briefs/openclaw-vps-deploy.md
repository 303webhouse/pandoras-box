# Codex Brief: Deploy OpenClaw to VPS (Proof-of-Concept Spike)

**Date:** February 19, 2026
**Priority:** High
**Scope:** VPS deployment only — zero changes to existing Pivot bot
**Estimated effort:** ~30 min agent time

---

## Context

Nick has OpenClaw installed locally on his Windows PC (version 2026.2.2-3) with auth profiles and device config at:

```
C:\Users\nickh\AppData\Roaming\npm\openclaw*
C:\Users\nickh\AppData\Roaming\npm\node_modules\openclaw\...
```

OpenClaw was originally intended to run on the VPS for 24/7 uptime, but a custom Python Discord bot ("Pivot") was built instead. We're now evaluating whether to migrate Pivot's functionality to OpenClaw. This spike deploys OpenClaw to the VPS **alongside** the existing bot so we can test it without risk.

**The existing Pivot bot must not be touched, interrupted, or affected in any way.**

---

## VPS Environment (verified February 19, 2026)

- **Host:** 188.245.250.2 (Hetzner PIVOT-EU)
- **OS:** Ubuntu 24.04.3 LTS
- **RAM:** 3.7 GB (3.2 GB available)
- **Disk:** 75 GB (70 GB free)
- **Node.js:** NOT INSTALLED — must install
- **Existing services:**
  - `pivot-bot.service` — custom Python Discord bot (LEAVE ALONE)
  - `pivot-collector.service` — data collector cron (LEAVE ALONE)
- **Existing bot runs as:** `pivot` user, working directory `/opt/pivot`

---

## Pre-requisites (Nick must do before Codex runs)

### 1. Create a NEW Discord Bot Application

Nick needs a second Discord bot token so OpenClaw doesn't conflict with the existing Pivot bot.

**Steps for Nick:**
1. Go to https://discord.com/developers/applications
2. Click "New Application" → name it "Pivot-Next" (or whatever you like)
3. Go to **Bot** tab → click "Reset Token" → copy the token and save it somewhere safe
4. Under **Privileged Gateway Intents**, enable ALL THREE:
   - Presence Intent ✅
   - Server Members Intent ✅
   - Message Content Intent ✅
5. Go to **OAuth2 → URL Generator**:
   - Select scopes: `bot`, `applications.commands`
   - Select permissions: `Send Messages`, `Read Messages/View Channels`, `Read Message History`, `Embed Links`, `Attach Files`, `Use Slash Commands`
6. Copy the generated URL, open it in browser, invite the bot to your Discord server
7. **Give Codex the new bot token** when running this brief

### 2. Create a test channel in Discord

Create a channel called `#pivot-next-test` (or similar) in your Discord server. This is where OpenClaw will post during testing. The existing Pivot bot continues using its current channels.

---

## Implementation Steps

### Step 1: Install Node.js on VPS

```bash
ssh root@188.245.250.2

# Install Node.js 22 LTS via NodeSource
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs

# Verify
node --version   # should show v22.x.x
npm --version    # should show 10.x.x
```

### Step 2: Install OpenClaw globally

```bash
npm install -g openclaw

# Verify
openclaw --version   # should show 2026.x.x
```

### Step 3: Create OpenClaw directory and user

```bash
# Create dedicated directory (separate from /opt/pivot)
mkdir -p /opt/openclaw
chown root:root /opt/openclaw

# OpenClaw stores config in the home directory of whoever runs it.
# Create a dedicated system user for isolation.
useradd --system --create-home --shell /bin/bash openclaw
```

### Step 4: Configure OpenClaw

```bash
# Switch to openclaw user
su - openclaw

# Initialize OpenClaw — this creates ~/.config/openclaw/ (or similar)
# Use the NEW Discord bot token from pre-requisites
openclaw init

# During init, provide:
# - Discord bot token: [THE NEW TOKEN FROM PRE-REQS]
# - LLM provider: OpenRouter
# - LLM API key: (same key from /opt/pivot/.env → LLM_API_KEY)
# - LLM model: anthropic/claude-sonnet-4.6
# - Default channel: #pivot-next-test

# If init is not interactive, configure via:
openclaw config set discord.token "NEW_BOT_TOKEN_HERE"
openclaw config set llm.provider "openrouter"
openclaw config set llm.apiKey "USE_KEY_FROM_PIVOT_ENV"
openclaw config set llm.model "anthropic/claude-sonnet-4.6"

# Exit back to root
exit
```

**IMPORTANT:** Both bots can share the same OpenRouter API key — OpenRouter doesn't restrict concurrent usage.

### Step 5: Test OpenClaw manually

```bash
# As openclaw user, verify it connects to Discord
su - openclaw
openclaw start --once   # or whatever flag does a single-run test

# Verify in Discord: the "Pivot-Next" bot should appear online in your server
# Send it a test message in #pivot-next-test
# Confirm it responds

# If it works, exit
exit
```

### Step 6: Create systemd service

Create `/etc/systemd/system/openclaw.service`:

```ini
[Unit]
Description=OpenClaw AI Agent (Pivot-Next)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=openclaw
WorkingDirectory=/home/openclaw
ExecStart=/usr/bin/openclaw start
Restart=always
RestartSec=15
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
```

**Note:** The `ExecStart` path may differ. Check with `which openclaw` after install. If OpenClaw uses a different start command (e.g., `openclaw run`, `openclaw serve`), adjust accordingly. Check `openclaw --help` for the correct long-running daemon command.

```bash
systemctl daemon-reload
systemctl enable openclaw
systemctl start openclaw

# Verify
systemctl status openclaw
journalctl -u openclaw -f   # watch logs, confirm Discord connection
```

### Step 7: Verify coexistence

After OpenClaw is running, verify the existing Pivot bot is unaffected:

```bash
# Both should show "active (running)"
systemctl status pivot-bot openclaw

# Check Pivot bot logs for any errors
journalctl -u pivot-bot --since "5 minutes ago"
```

In Discord:
- Existing Pivot bot should still be online and responding in its channels
- New OpenClaw bot should be online and responding in #pivot-next-test
- No duplicate messages or conflicts

---

## Definition of Done

- [ ] Node.js 22 LTS installed on VPS
- [ ] OpenClaw installed globally via npm
- [ ] OpenClaw running as `openclaw` systemd service
- [ ] OpenClaw connected to Discord with NEW bot token (not Pivot's token)
- [ ] OpenClaw responds to messages in #pivot-next-test channel
- [ ] Existing `pivot-bot` and `pivot-collector` services unaffected (still running, no errors)
- [ ] Both bots online simultaneously in Discord server

---

## What This Does NOT Include

- No migration of Pivot features to OpenClaw (that's Step 2, separate brief)
- No changes to existing Pivot bot code, config, or services
- No cron jobs or morning briefs in OpenClaw yet
- No intake/personality setup (we'll do that with Nick interactively after deploy)
- No shutdown of existing Pivot bot

---

## Troubleshooting

**OpenClaw won't start:** Check `journalctl -u openclaw -f` for errors. Common issues:
- Missing Node.js → verify `node --version` works as `openclaw` user
- Wrong token → re-run `openclaw config set discord.token`
- Port conflict → OpenClaw and Pivot use different Discord gateway connections (different tokens), so no port conflict expected

**Pivot bot breaks after OpenClaw install:** This should not happen since they're completely isolated (different users, different directories, different tokens). If it does, stop OpenClaw immediately: `systemctl stop openclaw` and check Pivot logs.

**OpenClaw version mismatch:** Nick's local machine has 2026.2.2-3. The npm install may pull a newer version. That's fine — use whatever npm gives you.

---

## Files Changed

- `/etc/systemd/system/openclaw.service` (NEW)
- `/home/openclaw/.config/openclaw/` (NEW — OpenClaw config directory)
- Node.js installed system-wide via apt

**Zero files changed in /opt/pivot/**
