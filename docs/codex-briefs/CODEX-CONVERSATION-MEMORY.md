# Codex Brief: Pivot Conversation Memory Fix

## Problem

Pivot has **zero conversation memory** in `#pivot-chat`. Every message creates a fresh, independent LLM call with no prior context. This causes three user-facing bugs:

1. **Context amnesia**: Pivot evaluates a trade in detail, then two messages later asks "what's your position?" as if the evaluation never happened.
2. **Date blindness**: The date IS injected into the system prompt by `pivot_agent.py`, but Gemini sometimes ignores system-prompt-only context. The model confabulated "TODAY: unavailable" despite the date being present.
3. **Screenshot disconnect**: The vision flow makes two separate LLM calls (extract → evaluate). Follow-up messages have zero context from either call.

All three reduce to one root cause: **no conversation history is passed between LLM calls**.

## Scope

**File to modify**: `backend/discord_bridge/bot.py` (live copy: `/opt/pivot/discord_bridge/bot.py`)

**Files NOT to modify**: `pivot/llm/pivot_agent.py`, `pivot/llm/prompts.py` — these are fine as-is.

## Architecture

### New class: `ConversationBuffer`

Add this near the top of `bot.py` (after imports, before command definitions).

```python
from collections import deque
from datetime import datetime, timezone, timedelta

class ConversationBuffer:
    """
    Per-channel rolling conversation history for LLM context.
    
    Stores (user_message, assistant_response) pairs. Automatically
    trims oldest entries when token budget is exceeded.
    """
    
    MAX_PAIRS = 10          # Max message pairs to retain
    TOKEN_BUDGET = 6000     # Approx token ceiling for history block
    
    def __init__(self):
        self._history: deque[dict] = deque(maxlen=self.MAX_PAIRS * 2)
        # Each entry is {"role": "user"|"assistant", "content": str}
    
    def add_user(self, content: str) -> None:
        self._history.append({"role": "user", "content": content})
    
    def add_assistant(self, content: str) -> None:
        self._history.append({"role": "assistant", "content": content})
    
    def get_messages(self) -> list[dict]:
        """
        Return message list trimmed to fit within TOKEN_BUDGET.
        Trims from the oldest messages first.
        """
        messages = list(self._history)
        # Simple token estimation: 1 token ≈ 4 chars
        while messages and self._estimate_tokens(messages) > self.TOKEN_BUDGET:
            # Remove oldest pair (user + assistant)
            if len(messages) >= 2:
                messages.pop(0)
                messages.pop(0)
            else:
                messages.pop(0)
        return messages
    
    def _estimate_tokens(self, messages: list[dict]) -> int:
        total_chars = sum(len(m["content"]) for m in messages)
        return total_chars // 4
    
    def clear(self) -> None:
        self._history.clear()


# Module-level buffer store keyed by channel ID
_conversation_buffers: dict[int, ConversationBuffer] = {}


def _get_buffer(channel_id: int) -> ConversationBuffer:
    if channel_id not in _conversation_buffers:
        _conversation_buffers[channel_id] = ConversationBuffer()
    return _conversation_buffers[channel_id]
```

**Note on token estimation**: Uses simple char-based estimate (chars / 4) which is good enough. Do NOT add `tiktoken` as a dependency.

### Modification 1: Date in user context (backup injection)

In the `#pivot-chat` handler's generic text path (the `if not reply:` block near line ~3058), the `prompt` variable currently looks like:

```python
prompt = (
    "Use this current market context when answering.\n\n"
    f"{market_context}\n\n"
    f"USER MESSAGE:\n{user_text or 'Give a quick market read.'}"
)
```

**Change to**: Prepend the date into market_context so it appears in the user message (not just system prompt). Add this before the prompt is built:

```python
from datetime import datetime, timezone, timedelta

et = timezone(timedelta(hours=-5))
now_et = datetime.now(et)
date_header = (
    f"TODAY: {now_et.strftime('%A, %B %d, %Y')} | "
    f"Time: {now_et.strftime('%I:%M %p')} ET"
)
market_context = f"{date_header}\n\n{market_context}"
```

This is a **backup** — `pivot_agent.py` already injects the date into the system prompt. This ensures the date appears in the user message too, where Gemini is less likely to ignore it.

### Modification 2: Switch chat handler to use `call_llm_messages` with history

The current generic chat path calls:
```python
reply = await call_pivot_llm(prompt, max_tokens=1600)
```

Replace this entire block with a history-aware flow:

```python
# --- History-aware chat ---
buffer = _get_buffer(message.channel.id)

# Build the current user message with market context
current_user_content = (
    f"Use this current market context when answering.\n\n"
    f"{market_context}\n\n"
    f"USER MESSAGE:\n{user_text or 'Give a quick market read.'}"
)

# Add to buffer BEFORE the call so it's in history
buffer.add_user(current_user_content)

# Build full message list: history + current
messages = buffer.get_messages()

if ticker_hint and _is_directional_question(user_text):
    # For high-stakes prompts, add the repeat instruction to the last message
    messages[-1] = {
        "role": "user",
        "content": _repeat_high_stakes_prompt(messages[-1]["content"]),
    }

reply = await call_pivot_llm_messages(messages, max_tokens=1600)

# Add assistant response to buffer
if reply and not reply.startswith("[LLM error"):
    buffer.add_assistant(reply)
```

### Modification 3: Vision flow adds to conversation buffer

In the vision/screenshot handling path (the `if not reply and image_attachment:` block), after the final reply is assembled, add the exchange to the buffer:

```python
# After: reply = f"**Image Extract**\n{image_analysis}\n\n**Contextual Evaluation**\n{contextual_eval}"
# Or after: reply = image_analysis (the fallback)

if reply:
    buffer = _get_buffer(message.channel.id)
    # Store what the user sent (their text + "[attached image]" note)
    user_summary = user_text or "[screenshot uploaded]"
    if image_attachment:
        user_summary += f"\n[Image: {image_attachment.filename}]"
    buffer.add_user(user_summary)
    buffer.add_assistant(reply)
```

This way, when Nick follows up with "what do you think about the IBIT position?" — the buffer already contains the evaluation.

### Modification 4: CSV/import flows also add to buffer

Same pattern — after the trade import preview or confirmation reply is built, add it to the buffer so Pivot remembers the import context.

```python
if reply:
    buffer = _get_buffer(message.channel.id)
    buffer.add_user(user_text or "[CSV attachment]")
    buffer.add_assistant(reply)
```

**Important**: Place this BEFORE the `if not reply:` generic text block, so the buffer gets populated in the correct flow.

## Flow Order in `on_message` (after changes)

The existing if/elif chain stays the same. The buffer writes happen at the END of each branch, right before `send_discord_chunks`. Here's the simplified order:

```
1. Trade import confirmation → reply + buffer.add
2. CSV import path → reply + buffer.add  
3. Pasted trade text → reply + buffer.add
4. Image/screenshot path → reply + buffer.add
5. Generic text path → buffer-aware call_llm_messages → buffer.add
6. send_discord_chunks(reply)
```

## What NOT to change

- **`pivot_agent.py`** — The `_build_openrouter_payload` function already handles system prompt + date injection. Don't duplicate this logic.
- **`prompts.py`** — System prompt is fine as-is.
- **Max tokens** — Keep existing limits. The conversation history is budget-managed by `ConversationBuffer.TOKEN_BUDGET`.
- **Other channels** — Only `#pivot-chat` gets conversation memory. Whale alerts, UW flow, crypto alerts are all single-shot evaluation flows and should stay that way.

## Testing

After deploying, verify these scenarios in `#pivot-chat`:

1. **Basic memory**: Send "What's the bias?" → get answer → Send "Why?" → Pivot should explain the bias reasoning without asking what you're referring to.
2. **Screenshot continuity**: Upload a screenshot → get analysis → Ask "what do you think about that?" → Pivot should reference the analysis.
3. **Date awareness**: Ask "what's today's date?" → Pivot should answer correctly without hedging.
4. **Buffer limits**: Send 15+ messages → Pivot should still respond coherently (oldest context gets trimmed, not crash).

## Deployment

```bash
# After pushing to main:
ssh root@188.245.250.2
cd /opt/pivot && git pull origin main
systemctl restart pivot-bot
journalctl -u pivot-bot -f  # verify clean startup, no import errors
```

## Definition of Done

- [ ] Pivot remembers context from the last ~8-10 messages in `#pivot-chat`
- [ ] Follow-up questions after screenshot analysis work without re-explaining
- [ ] Pivot correctly states today's date when asked
- [ ] No new dependencies required (char-based token estimation, no tiktoken)
- [ ] No changes to `pivot_agent.py` or `prompts.py`
- [ ] Clean bot restart with no import errors
