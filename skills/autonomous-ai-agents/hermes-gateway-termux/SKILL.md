---
name: hermes-gateway-termux
description: "Use when Telegram bot won't connect or reply on Termux."
version: 1.0.0
---

# Hermes Gateway on Termux — Troubleshooting

## When to use
Use when the user says "Telegram bot not responding", "can't connect to Telegram", "bot doesn't reply", or any Telegram gateway failure on Termux. Also use when changing models/providers and cron jobs start failing closed.

## 1. Check gateway status first
```bash
hermes gateway status
# ✗ Gateway is not running
```

If not running, start in background:
```bash
hermes gateway run        # foreground
# Use terminal(background=true) in agent sessions
```

**Note:** `hermes gateway start` does NOT work on Termux — always use `hermes gateway run`.

## 2. Gateway is running but Telegram bot doesn't respond
Check gateway log:
```bash
tail -30 ~/.hermes/logs/gateway.log
```

Look for:
- `✓ telegram connected` — gateway connected to Telegram API
- `Disconnected from Telegram` — was shut down, needs restart
- `Telegram network error` — intermittent connectivity (usually self-heals)
- `Rehydrated persisted /model override for session=agent:main:telegram:dm:<chat_id>` — session has a pinned model override that survived restart

Also check errors.log:
```bash
tail -30 ~/.hermes/logs/errors.log
```

## 3. Provider model 403 errors
If errors.log shows:
```
openai.PermissionDeniedError: Error code: 403
{'error': {'code': 'access_denied', 'message': 'Access restricted. Deposit required to unlock premium models.'}}
```

The configured model is blocked by the provider. Fix:
- **Change default model**: `hermes config set model.default <working-model>`
- **Verify available models** in `~/.hermes/config.yaml` under the provider's `models:` section
- Common pattern: api.b.ai blocks `deepseek-v4-pro`, `glm-5.3`, `glm-5.3-flash` — only `deepseek-v4-flash` works without deposit

## 4. Per-session model override persists
A `/model` override in a Telegram session is stored in `~/.hermes/sessions/sessions.json`:
```json
"agent:main:telegram:dm:<chat_id>": {
  "model_override": {"model": "glm-5.3-flash", "provider": "custom:api.b.ai", "base_url": "https://api.b.ai/v1"},
  ...
}
```

If the overridden model is blocked, the bot will connect but fail to respond. The gateway log mentions `Rehydrated persisted /model override` — that's your signal.

**Fix:** delete the `model_override` key from the session entry, then restart gateway.

## 5. Cron model_snapshot mismatch
Changing `model.default` triggers:
```
1 enabled unpinned cron job has stored model_snapshot values that differ from the new global model.
They will fail closed on their next run instead of silently using the changed model/provider.
```

The cron job's stored `model_snapshot` lives in `~/.hermes/cron/jobs.json` — even when model=None (unpinned). The `cronjob` tool's `update` action does NOT clear this snapshot.

**Fix — pin the cron to an explicit model:**
```bash
hermes cron edit <job_id> --model <model> --provider <provider>
```
This recalculates the snapshot and the job will no longer fail closed.

## 6. Full diagnosis flow
```
1. hermes gateway status              → running?
2. tail -30 ~/.hermes/logs/gateway.log → ✓ telegram connected?
3. tail -30 ~/.hermes/logs/errors.log  → 403/API errors?
4. Check ~/.hermes/sessions/sessions.json for model_override
5. hermes cron list                    → stale model_snapshot?
6. Fix → restart gateway → test
```

## Pitfalls
- `hermes gateway start` does not exist on Termux — always use `hermes gateway run`
- The `cronjob` tool's `update` action does NOT refresh stale `model_snapshot` — must use `hermes cron edit --model/--provider`
- Session model overrides survive restarts — check sessions.json when the bot connects but doesn't reply
- Changing the default model does NOT retroactively fix cron jobs with stale snapshots
- Gateway log appends to the same file; tail reads latest entries — don't be misled by old entries on first run