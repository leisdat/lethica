# Tokenin.my.id provider on 9Router (Termux, 2026-08)

Working example of adding an OpenAI-compatible provider whose model names MUST
include the provider prefix. Uses the **double-prefix trick**.

## Provider info

- **Base URL**: `https://tokenin.my.id/v1`
- **Node**: `openai-compatible-chat-<uuid>`, prefix `myt`, type `openai-compatible`
- **Models**: 86 total, all prefixed `myt/` (e.g. `myt/gpt-5-mini`). GPT-5.x,
  Claude 4.5-5, Gemini 3.x, Grok, Kimi, GLM, DeepSeek, Qwen, MiniMax.
- **Pricing**: per-model Rupiah per 1M tokens (input/output/cache). Some models
  are FREE (Rp 0) with an RPM cap (1-3 req/min).

## The gotcha: upstream REQUIRES the prefix in the model name

Testing the model list via `/v1/models` works (returns `myt/gpt-5-mini`, etc.),
but a chat call to `myt/gpt-5-mini` fails with:

```
[openai-compatible-chat-<uuid>/gpt-5-mini] [400]: {"error":{"message":
"Model tidak diizinkan untuk kunci ini. Pilih salah satu: myt\/gpt-5-mini, ..."}}
```

Root cause: 9Router strips the first prefix before forwarding — the upstream
receives `gpt-5-mini`, but tokenin's API requires the full `myt/gpt-5-mini`.

**Fix**: request with a doubled prefix → `myt/myt/gemini-3.5-flash-free`.
9Router strips ONE `myt/`, forwards `myt/gemini-3.5-flash-free`, upstream accepts.

Verified working:
- `myt/myt/gemini-3.5-flash-free` — 3 req/min, FREE
- `myt/myt/gpt-5.6-sol-free` — 1 req/min, FREE
- `myt/myt/claude-opus-4-8-free` — 1 req/min, FREE
- `myt/myt/mimo-v2.5-free` — 3 req/min, FREE

Failed at time of test ("Saldo tidak cukup" / insufficient_balance even though
FREE): `myt/grok-4.6-free`, `myt/deepseek-v4-pro-free` — do not add to combos.

## Combo registration

These were appended to the `Free-All` combo's `models` JSON as
`"myt/myt/gemini-3.5-flash-free"` (etc.) so they act as fallbacks after the
higher-priority free providers. Remember: combo `models` order = priority, and
each entry must be the DOUBLE-prefixed form.

## Diagnostic path that worked

1. `curl https://tokenin.my.id/v1/models -H "Authorization: Bearer sk-..."` →
   list model IDs, confirm provider is reachable and see the `myt/` prefix.
2. Direct chat call to tokenin WITH prefix → confirms the correct model string.
3. Chat call through 9Router with single prefix → read the `[400]` error; the
   upstream echoes which model strings it accepts, revealing the prefix requirement.
4. Retry through 9Router with doubled prefix → success.

## Notes / unresolved

- A prior attempt to add `morphllm.com` with an identical DB shape FAILED to
  link ("No active credentials for provider: morph") even after adding
  `nodeName`, `priority=1`, etc., and was removed. tokenin linked first try.
  The root cause for morph was never found. If a new provider doesn't link
  despite a correct-looking DB row, consider: stale combo references, a
  conflicting prefix in another table, or the node/connection not being read on
  boot — and don't burn hours; the double-prefix + DB schema above is the
  known-good path, and removing a broken provider is acceptable.
