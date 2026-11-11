# language-lock

**Your agent answers in your language, and stays there.**

Models drift between languages:
- A long English conversation suddenly continues in Chinese after a tool returned Chinese text ([hermes-agent#130117](https://github.com/NousResearch/hermes-agent/issues/130117)).
- A Spanish chat on Telegram gets English replies after a few code turns.
- The drift then sticks for the rest of the conversation.

Language Lock notices and pulls the agent back:

```text
you:    Please look at the logs and tell me why the upload is failing.
agent:  上传失败是因为令牌已过期。我已经刷新了令牌……          <- drifted into Chinese
you:    why did that happen?

[Language Lock] Your last reply was in Chinese, but the user writes in English. Reply in English
from now on. Keep code, commands, file names and quoted text exactly as they are.

agent:  The upload failed because the token had expired...
```

## How it works

1. **It learns your language** from your last five messages, or uses one you set. If you switch languages, it follows you.
2. **It checks every reply's language without a model.**
   - Writing systems identify Chinese, Japanese, Korean, Russian, Ukrainian, Arabic, Persian, Hindi, Thai, Greek and Hebrew.
   - Common words tell apart English, Spanish, French, German, Portuguese, Italian, Dutch, Indonesian and Turkish.
   - Code blocks, inline code, links, emails and file names are ignored, so a Spanish reply full of English code still reads as Spanish.
3. **When a reply drifted,** the agent is told at the start of the next turn to switch back, and the drift is counted.
4. **Asking for another language on purpose is respected.** "Translate this into French", "answer in English", "en español" and "auf Deutsch" are never counted as drift.

## Use it

```text
/lang               your language, the last reply's language, drifts caught and corrected
/lang set es        always expect Spanish in this session (a code or a name)
/lang auto          learn it from your messages again
```

```yaml
plugins:
  entries:
    language-lock:
      settings:
        language: ""      # e.g. "hi" or "Hindi"; empty learns it from your messages
        remind: drift     # drift: only after a drift; always: remind every turn
```

## What it touches

- **Reads your messages and the agent's replies** to detect their language, in memory, per session. Nothing is written to disk.
- **Adds one sentence of context** (through `pre_llm_call`) after a drift, or every turn with `remind: always`.
- **No model calls, no network, no dependencies.**

## Limits

- **The fix comes on the next turn.** A reply that already drifted is not rewritten. Rewriting would need a model call and would hold back streaming.
- **20 languages.** Others are ignored, never mistaken for drift.
- **Long text:** only the first 4,000 characters of a message or reply are read, which is plenty to tell the language and keeps pasted logs from slowing anything down.
- **Very short messages** ("ok", "👍") don't count toward your language.
- **Compaction summaries** ([#135470](https://github.com/NousResearch/hermes-agent/issues/135470)) are written by Hermes's auxiliary model, which plugins can watch but not steer. That one needs a core fix.

## Development

```bash
pytest tests
```

26 tests cover long and hostile input staying fast, detecting 11 languages, ignoring code and links, drift and correction, intentional translation, a user switching languages, the settings and the commands.

## License

MIT
