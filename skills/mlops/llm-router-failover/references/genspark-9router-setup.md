# Genspark + 9Router setup (Termux, 2026-08)

Live reference for the Genspark llm_proxy provider added to 9Router on this
user's Termux setup. Update if the patch is reapplied after a 9Router upgrade
or provider config changes.

## Provider info

- **Base URL**: `https://www.genspark.ai/api/llm_proxy/v1`
- **Key**: stored in `~/.genspark-tool-cli/config.json` (field `api_key`)
- **Models**: 53, all prefix `gs/` (e.g. `gs/claude-opus-5`, `gs/gpt-5.6-luna`)
- **Top models**: opus-5, sonnet-5, fable-5, gpt-5.6-luna[-max], grok-4.6, opus-4.8, kimi-k3, deepseek-v4-pro, gpt-5.3-codex
- **Quirk**: returns `data: [DONE]` tail after the final JSON chunk (needs tolerant JSON parser)

## 9Router DB entries

### `apiKeys`
The Genspark key (gsk-eyJ...) was added as a valid key — Hermes sends this key
as Bearer, and 9Router accepts it.

### `providerNodes`
- **Name**: Genspark
- **Prefix**: `gs`
- **Type**: `openai-compatible-chat-<uuid>`
- **Data**: `{"prefix":"gs","apiType":"openai-compatible","baseUrl":"https://www.genspark.ai/api/llm_proxy/v1"}`

### `providerConnections`
- Auth type: `api_key` (the key field stores the actual gsk-... credential)
- Active: 1

### `combos`
- **Free-All** (kind=`combo`): 86 models, 8 providers:
  `gs/` 46, `kr/` 17, `cag/` 11, `tabi/` 3, `bai/` 3, `gg/` 4, `or/` 1, `gcli/` 1
  Priority order: gs/ first (best models), then kr/, bai/, cag/, gg/, tabi/,
  gcli/, or/.
- **Free-Kombo** (kind=`combo`): 35 models, all `kr/` + `gcli/` — working, no
  Genspark dependency.

## The 8910.js combo runner patch (re-apply on 9Router update)

File: `/data/data/com.termux/files/usr/lib/node_modules/9router/app/.next-cli-build/server/chunks/8910.js`
Backup: `~/.9router-backup-8910-v2.js` (last known-good patched version)

The patch replaces the `if(b.ok)return` guard in the `q()` (Pr) function with
a billing-text check. Use `b.clone().text()` (NOT `.json()` — text works on
both JSON and SSE bodies). Detection patterns (lowercased):
- `credit` AND `exhaust` both present
- `insufficient_quota` present
- `billing_error` present

If billing text is detected, the code does NOT return `b` — it falls through to
the existing error handler, which calls `hk(status, errorMsg)` → default
`shouldFallback: true` → tries the next model in the combo.

After patching, restart 9Router (`kill -9` both 9router and next-server, then
`9router -n --skip-update`). Verify with a direct curl request to the combo
name — it should skip the exhausted provider and answer from a working one.

## Hermes config

```yaml
model:
  default: Free-All
  provider: custom
  base_url: "http://127.0.0.1:20128/v1"   # /v1 REQUIRED
  api_key: "gsk-..."                      # same key added to 9Router apiKeys
  aliases:
    opus5: custom/gs/claude-opus-5
    sonnet5: custom/gs/claude-sonnet-5
    fable: custom/gs/claude-fable-5
    luna: custom/gs/gpt-5.6-luna
    lunamax: custom/gs/gpt-5.6-luna-max
    grok46: custom/gs/grok-4.6
    opus48: custom/gs/claude-opus-4-8
    gpt55: custom/gs/gpt-5.5
    codex53: custom/gs/gpt-5.3-codex
    kimi3: custom/gs/kimi-k3
```

Note: the `model.aliases` string form (`custom/gs/...`) uses the current
`model.base_url` (9Router). For per-alias `base_url` override, use the
`model_aliases:` dict form which supports `model`, `provider`, `base_url`
but NOT `api_key` (falls through to the custom provider's `model.api_key`).

## Quirks

- Genspark returns 200 OK with "Your Genspark credits have been exhausted" in
  `choices[0].message.content` when credits are depleted — not an HTTP error.
  This requires the 8910.js patch to translate into a failover signal.
- 9Router combo `kind` must be `'combo'` (not `None`/`NULL`) for the combo
  runner to activate failover. `kind=NULL` → plain model list, direct route.
- The combo models JSON array is priority-ordered: first = most preferred.
  Providers are tried in order; exhausted ones are skipped (with patch) or
  block the whole combo (without patch).