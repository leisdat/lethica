# Routerku v6 — Architecture Map

`~/routerku/router.mjs` — 1316 lines, single file, zero npm deps (Node ≥ 20 stdlib only).

## Top-of-file constants & globals (lines 1-100)

| Symbol | Purpose |
|---|---|
| `PORT` (18) | `process.env.ROUTERKU_PORT \|\| 20130` |
| `DB_PATH` (19) | `process.env.ROUTERKU_DB \|\| ~/.9router/db/data.sqlite` |
| `TIMEOUT_MS` (20) | default upstream fetch timeout 45000 |
| `CACHE_PATH`/`LOG_PATH`/`TOKENS_PATH` (21-23) | persistent file paths |
| `tgAlert` (28-50) | Telegram notification helper, 5-min cooldown per kind |
| `providers` (96) | `[{id, prefix, name, baseUrl, apiType, keys, active}]` |
| `combos` (97) | `{name: [modelId...]}` map |
| `authKeys` (98) | `Set` of valid bearer tokens for client auth |
| `cooldowns` (99) | `Map prefix -> untilMs` |
| `circuitState` (100) | `Map prefix -> {state, failCount, openSince, lastFail}` |
| `rpmLog`/`rpdLog` (101-102) | rate-limit windows |
| `requestLog` (103) | ring buffer, ~200 entries |
| `providerStats` (104) | `{prefix: {tokensIn, tokensOut, healthStatus, …}}` |
| `consecutiveDown` (105) | `Map prefix -> int` (used by v6 self-trip) |
| `providerHealth` (106) | `Map prefix -> {ewma, fails}` (latency) |
| `respCache` | `Map sha -> {response, expiresAt}` |
| `cumulativeTokens` | `{in, out, compactCount}` persisted to disk |

## AES key encryption (37-87)

`encryptKey(plaintext, passphrase)` / `decryptKey(ciphertext, passphrase)`:
- Algorithm: `crypto.createCipheriv('aes-256-gcm', key, iv)`
- Output format: `iv:tag:ciphertext` (all hex)
- Key derivation: `scryptSync(passphrase, salt, 32)`
- Salt + passphrase from `~/.routerku.key` + `ROUTERKU_KEY` env

## DB load & provider discovery (200-300)

`loadDb()`:
- Open `DatabaseSync(DB_PATH)`
- SELECT nodes: `json_extract(data, '$.prefix')`, `$.baseUrl`, `$.apiType`
- SELECT connections: `$.providerSpecificData.prefix`, `$.apiKey` (decrypted)
- Build `providers[]` + `combos{}`
- Called on boot AND on `fs.watchFile` change (2s interval)

`discoverModels()` (598-622):
- For each provider, GET `{baseUrl}/models` with API key
- Populate `provider.models[]`
- Cache to `~/.routerku-models.json` (TTL 24h) — boot uses cache, refreshes in background
- Concurrent fan-out via `Promise.all`

## Health probe & circuit breaker (110-220 + 923-997)

`checkProviderHealth()` (called every 60s):
- For each provider: GET `{baseUrl}/models` with 5s AbortController timeout
- On success: update `providerHealth[pfx].ewma`, reset `consecutiveDown`
- On `up` + circuit OPEN: **auto-delete** circuit entry, log "circuit CLOSED"
- On failure: increment `consecutiveDown[pfx]`
- If all providers have `consecutiveDown >= 3`: append `self-trip` line to `watchdog.log`
  + fire `tgAlert('self-trip', …)`

Circuit breaker states (200-220):
- CLOSED: normal
- OPEN: skip in `handleChat` cascade; auto-close on health-probe success
- 3 consecutive 5xx → OPEN for 60s, exponential backoff up to 600s

## Handler dispatch (1004-1270)

`http.createServer` switch on `req.method + url.pathname`:

| Path | Method | Handler |
|---|---|---|
| `/` | GET | static `dashboard.html` |
| `/health`, `/api/health` | GET | light no-auth `{ok, status, up, total, uptime}` |
| `/api/status` | GET | full provider state snapshot |
| `/api/stats` | GET | per-prefix req/ok/fail + recent log |
| `/api/stats/clear` | POST | reset requestLog + providerStats + cumulativeTokens |
| `/api/log` | GET | persistent log lines (`?n=200`) |
| `/api/reload` | POST | manual DB reload |
| `/api/circuit/reset` | POST | clear all circuit states |
| `/api/cache/stats` / `/api/cache/clear` | GET/POST | response cache management |
| `/v1/models` | GET | OpenAI-compat list of `prefix/modelId` |
| `/v1/chat/completions` | POST | handleChat (cascade + streaming) |
| `/v1/embeddings` | POST | handleEmbeddings (added in v6.1) |

## `handleChat` cascade (722+)

```js
const candidates = combos[requested] ? combos[requested] : [requested];
for (const modelId of candidates) {
  // 1. parse prefix/model
  // 2. skip if cooldown/circuit-open
  // 3. fetch upstream with AbortController + per-prefix timeout
  // 4. stream? re-stream SSE bytes
  // 5. non-stream: parse + return JSON, update stats
  // 6. on !ok: mark fail, try next candidate
}
```

Per-prefix timeout (`getTimeout(prefix)`) — defaults to `TIMEOUT_MS` but
overridable per prefix (e.g. big models get 90s).

## `handleEmbeddings` cascade (722-784)

Same pattern as `handleChat` but:
- Always non-stream
- Body passthrough except `model` rewritten to upstream model id
- No response cache (embeddings are cheap to compute, cache adds memory pressure)

## Auto-compact (305-348)

Triggered when cumulative input tokens > `MAX_INPUT_TOKENS` (default 100 000):
- Keep system message (if any)
- Keep first user message
- Keep last `COMPACT_KEEP_TAIL` messages (default 12)
- Digest middle: each message → `role: 90-char preview`
- If compacted is bigger than original → revert (guard)

## Response cache (532+)

Key: `sha256(model + JSON.stringify(messages) + temperature)`
TTL: 1 hour
Max: 500 entries
Persist on SIGINT/SIGTERM to `~/.routerku-cache.json`
Bypass: `body.cache === false` OR `body.stream === true`

## Token tracking & persistence (270-280)

`cumulativeTokens = {in, out, compactCount}` — debounced 3s save to
`~/.routerku-tokens.json`. Reset on `POST /api/stats/clear`.

## Persistent log (225-255)

`fs.createWriteStream(LOG_PATH, { flags: 'a' })`. Each line is JSON
`{t, prefix, model, ok, status, ms, err, tokens}`. 5MB cap → rotate
`requests.log.1 .2 .3` (keep 3).

## Watchdog (external, ~/routerku/watchdog.sh)

`crontab` every 2 min: `curl /health` → if substring `"ok":true` absent →
`pkill -f 'node router.mjs'`, `sleep 1`, `nohup node router.mjs &`.
Reads `watchdog.log` for `self-trip` lines (router appends these, not the
watchdog itself).

## Boot sequence (1167-1185)

```js
loadDb();              // read 9Router SQLite
loadRespCache();       // restore cache from disk
await discoverModels();// refresh models (cached)
watchDb();             // fs.watchFile 2s for live updates
checkProviderHealth(); // initial probe
setInterval(checkProviderHealth, 60_000);
// SIGINT/SIGTERM → flush tokens + cache, exit
server.listen(PORT, '0.0.0.0', () => console.log(...));
```

## Lines added by v6 / v6.1

- v6 (`checkProviderHealth` upgrade + `/health` endpoint): ~+30 lines
- v6.1 (`tgAlert` + `handleEmbeddings` + route): ~+100 lines

Original v3 baseline: 1186 lines. Current v6.1: 1316 lines.
