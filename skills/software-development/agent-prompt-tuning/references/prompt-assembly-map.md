# Hermes System Prompt Assembly Map (verified against source)

Source: `agent/system_prompt.py` + `agent/chat_completion_helpers.py` + `agent/agent_init.py` in `~/.hermes/hermes-agent/`.

## Layer Order (from file to API call)

```
SOUL.md (~/.hermes/SOUL.md)
  ↓
load_soul_md()
  ↓
build_system_prompt_parts()
  ├── stable   → SOUL.md (or DEFAULT_AGENT_IDENTITY)       [system_prompt.py:480-487]
  │               + tool guidance, task completion guidance,
  │               + parallel tool call guidance, memory guidance
  │
  ├── context  → coding workspace (AGENTS.md)
  │               + system_message (config agent.system_prompt)  [system_prompt.py:881-882]
  │               + context files
  │
  └── volatile → skills index
                  + memory snapshot (MEMORY.md + USER.md)
                  + timestamp
       ↓
build_system_prompt() → _cached_system_prompt     [system_prompt.py:1028]
       ↓
chat_completion_helpers.py:
  effective_system = agent._cached_system_prompt or ""
  if agent.ephemeral_system_prompt:
      effective_system += "\n\n" + agent.ephemeral_system_prompt   [chat_completion_helpers.py:3045-3047]
  api_messages = [{"role": "system", "content": effective_system}] + rest
       ↓
Provider/Model (model-side alignment is the final layer)
```

## Key Facts

| Fact | Source Line | 
|------|-------------|
| **SOUL.md is NOT overridden by config** — it's in stable tier, config system_message is in context tier (additive) | `system_prompt.py:480-483` vs `881-882` |
| **config `agent.system_prompt` → `system_message` → context tier** — appended after workspace, before context files | `system_prompt.py:881-882` |
| **Top-level `system_prompt:` key in config.yaml is DEAD** — must be under `agent:` to be read | Config structure, not in config_defaults.py |
| **`ephemeral_system_prompt` injected at API-call time** — appended AFTER cached prompt, NOT cached | `chat_completion_helpers.py:3045-3047` |
| **ephemeral source resolution** — env `HERMES_EPHEMERAL_SYSTEM_PROMPT` wins → `display.personality` → `agent.system_prompt` | `config.py:resolve_ephemeral_system_prompt_from_config()` + `personality.py:150` |
| **`prefill_messages_file` → prefill.json** — loaded as user+assistant priming messages, inserted at API-call time | `chat_completion_helpers.py:3053` |
| **`_cached_system_prompt` is cached for session lifetime** — changes to SOUL.md/config only take effect on new session | `system_prompt.py:447-451` |
| **Model-side safety behavior is the final arbitter** — prompt chain being intact does NOT guarantee model compliance | Proven by debugging: all layers verified, refusal still happened |

## Debug Procedure

When Hermes refuses despite aggressive SOUL.md/config:

1. Verify SOUL.md exists + content: `ls -la ~/.hermes/SOUL.md`
2. Verify config system_prompt is under `agent:` (not top-level): `grep -n "^agent:" ~/.hermes/config.yaml`
3. Check ephemeral sources: `env \| grep HERMES_EPHEMERAL`
4. Check provider/model: `grep -nE "^(model|provider):" ~/.hermes/config.yaml`
5. If all layers are intact, the refusal is **model-side** — change provider/model, not SOUL.md