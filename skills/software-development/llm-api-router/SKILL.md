---
name: llm-api-router
description: Build/maintain zero-dep Node LLM router with combo failover.
---

# Zero-dependency LLM API Router (Node)

A self-contained, ~1300-line Node `http.createServer` that sits in front of
many LLM provider APIs and presents a single OpenAI-compatible surface to
clients. Designed for Termux/Android (no systemd, no Docker, no native
modules). Verified at `~/routerku/router.mjs`.

## When to use

- You have N free-tier LLM API keys (or paid keys with quota) and want one
  unified endpoint that cascades through them on failure.
- You need OpenAI-compat surface (`/v1/chat/completions`, `/v1/embeddings`,
  `/v1/models`) but your providers are not all OpenAI — some are
  Anthropic-shaped, some are HTTP-only, some are remapped by new-api
  front-ends.
- You need to run on a phone/embedded without Docker/native modules.
- You already have a 9Router SQLite DB (`~/.9router/db/data.sqlite`) of
  provider nodes + connections; the router reads it directly.

## Architecture (routerku v6, 1316 lines)

```
incoming HTTP → url parse → handler router →
  ├─ /v1/chat/completions → handleChat
  │    ├─ combos[model]? → expand → for each candidate
  │    │    ├─ skip if cooldown/circuit-open
  │    │    ├─ fetch upstream with timeout + AbortController
  │    │    ├─ on !ok: mark fail, try next
  │    │    └─ on ok: return response
  │    └─ streaming: re-stream SSE bytes verbatim
  ├─ /v1/embeddings → handleEmbeddings (same cascade pattern)
  ├─ /v1/models → list all known models
  ├─ /api/status, /api/stats, /api/circuit/reset, /api/reload, …
  ├─ /health (no auth) — light, backward-compat with old watchdogs
  └─ static dashboard.html
```

Single `router.mjs` (Node ≥ 20, uses `node:sqlite` from stdlib — no npm).
Reads `~/.9router/db/data.sqlite` for provider list and watches the file
(`fs.watchFile` 2s) to auto-reload when the user adds a provider in the
dashboard.

## Critical design choices

### 1. Sticky first-hit, no random load balancing
Free providers (gr/claude-opus-5, or/minimax-m3:free, bai/qwen3.8-flash)
have very different quotas and latencies. A simple round-robin wastes
quota on slow providers. The pattern that works: **try the candidates in
list order; on first success, return; on fail, advance**. This means
when `minimax-m3:free` is fast, every call uses it; only when it
fails/cooldowns does traffic move to the next. Side effect: it
**looks like the router is "stuck" on one model** in rotation tests —
that's the point.

### 2. Skip cooldown/circuit-open by inline check, not by filtering
```js
if (cooldowns.get(pfx) && cooldowns.get(pfx) > Date.now()) continue;
const cs = circuitState.get(pfx);
if (cs && cs.state === 'OPEN') continue;
```
Calling helper functions (`isOnCooldown(pfx)`) that don't exist is the
#1 bug source. Inline the check.

### 3. AES-256-GCM encryption for keys at rest
API keys in SQLite are encrypted with a passphrase (`ROUTERKU_KEY` env
var or `~/.routerku.key`). Format: `iv:tag:ciphertext` (hex). On boot,
read all `providerConnections` and decrypt into a `keys[]` array per
provider. Never write the decrypted key to disk or logs. Rotate by
re-encrypting the whole DB.

### 4. Health-probe → auto-recover + self-trip
`checkProviderHealth()` runs every 60s. On each ping:
- mark `providerHealth[pfx].ewma` (latency in ms)
- on `up` + circuit OPEN → **auto-close the circuit** (recovery proactive)
- on `down` → increment `consecutiveDown[pfx]`
- if **all** providers down ≥3 consecutive probes → append a `self-trip`
  line to `watchdog.log`. The external watchdog reads this and restarts.
  The router itself doesn't `process.exit` (that would be the opposite
  of self-healing — let the watchdog decide).

### 5. Backward-compat `/health` response shape
Watchdog scripts commonly do `[[ "$HEALTH" == *'"ok":true'* ]]`. Changing
`/health` to return `{status: "ok"}` instantly kills the router in a
2-min restart loop. Always include the legacy boolean:
```js
res.end(JSON.stringify({
  ok: up > 0,        // ← legacy field, keep
  status, up, total, uptime,
}));
```
Also see `termux-node-projects` SKILL.md "Self-healing long-lived services"
for the full `/health` + watchdog pattern.

### 6. Auto-compact messages to prevent context overflow
If cumulative estimated input tokens exceed threshold (default 100 000),
digest the middle of `messages[]` (keep system + first user + last N),
preserving context shape. Heuristic: 1 token ≈ 4 chars latin. A model
that loops/regurgitates is almost always because its context is
truncated; auto-compact prevents that without the client knowing.

### 7. Response cache (identical non-stream requests)
Key by `sha256(model + JSON.stringify(messages) + temperature)`.
TTL ~1h, max 500 entries, persist to `~/.routerku-cache.json` on exit.
Bypass with `{"cache": false}` or streaming (`stream: true`).
Huge quota saver for "what's the weather" / "say hi" type calls.

### 8. Persistent log rotation
5MB cap on `~/.routerku-requests.log`, rotate `.1 .2 .3` and keep 3.
Use `fs.createWriteStream(LOG_PATH, { flags: 'a' })` for hot path;
check size on each write, cheap.

## Telegram alert pattern (routerku `tgAlert`)

```js
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';

let TG_TOKEN = process.env.ROUTERKU_TG_TOKEN || '';
let TG_CHAT  = process.env.ROUTERKU_TG_CHAT_ID || '5952002197';  // Home channel
const TG_ENABLED = process.env.ROUTERKU_TG !== '0';
if (!TG_TOKEN) {
  try { TG_TOKEN = fs.readFileSync(path.join(os.homedir(), '.hermes', 'agent_bot_token'), 'utf8').trim(); } catch {}
}
const TG_COOLDOWN_MS = 5 * 60_000;
const tgLastSent = new Map();
function tgAlert(kind, text) {
  if (!TG_ENABLED || !TG_TOKEN) return;
  const now = Date.now();
  if (now - (tgLastSent.get(kind) || 0) < TG_COOLDOWN_MS) return;
  tgLastSent.set(kind, now);
  const body = JSON.stringify({ chat_id: TG_CHAT, text: `🤖 [routerku] ${text}`, disable_web_page_preview: true });
  const req = https.request({
    hostname: 'api.telegram.org', port: 443, method: 'POST',
    path: `/bot${TG_TOKEN}/sendMessage`,
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    timeout: 5000,
  });
  req.on('error', () => {});  // silent — alert must never crash the router
  req.on('timeout', () => req.destroy());
  req.write(body); req.end();
}
```

Invariants:
- **Read token from file, never from env/cmdline** — env vars get
  redacted to `…` (U+2026) on Termux and break the request with
  `UnicodeEncodeError`. See `telegram-bots` SKILL.md for the
  full gotcha.
- **Cooldown per kind** — same incident shouldn't spam. 5 min is
  enough that a provider that flaps gets ≤ 12 messages/hour.
- **Silent `req.on('error')`** — Telegram being down must not take
  the router down. Log to console for debugging, that's it.

## Restart & kill hygiene

- **Never `pkill -f 'node router.mjs'` from the launching shell** —
  the pattern matches the shell's own command line. Use
  `pgrep -af 'node router.mjs'` first, verify with `ps -o pid,args
  -p <pid>`, then `kill -9 <pids>`.
- **Race on restart**: if the watchdog's `kill` + `nohup node … &`
  fires while a previous instance is still on port 20130, the new
  one crashes with `EADDRINUSE`. Always `sleep 2` between kill and
  relaunch, and tail the log for the new PID.

## 9Router DB schema (for SQLite reads)

```sql
-- provider nodes (one per upstream API)
SELECT json_extract(data, '$.prefix')  AS prefix,
       json_extract(data, '$.baseUrl') AS baseUrl
FROM providerNodes
WHERE json_extract(data, '$.prefix') IS NOT NULL
GROUP BY prefix;

-- provider connections (one or more per node, each with an API key)
SELECT json_extract(data, '$.providerSpecificData.prefix') AS pfx,
       json_extract(data, '$.apiKey')                       AS apiKey
FROM providerConnections
WHERE json_extract(data, '$.providerSpecificData.prefix') IS NOT NULL;

-- combos
SELECT name, models FROM combos;  -- models is JSON array string
```

`apiKey` may be AES-encrypted (prefix `enc:` or `v2:` depending on
9Router version). Decrypt with the same `ROUTERKU_KEY` you set when
the 9Router dashboard saved them.

## Pitfalls found the hard way

| Symptom | Cause | Fix |
|---|---|---|
| EADDRINUSE on restart | watchdog kill + relaunch races | `sleep 2` between kill and start |
| `EAI_AGAIN` random | Termux resolver flakes | Cloudflare DoH fallback (see `termux-node-projects`) |
| `HTTP 403 error 1010` | default Python/Node UA flagged by CF | send real browser UA + `Accept: application/json` + `Origin` |
| `EADDRINUSE` + old routerku process orphan | `node router.mjs &` survived `pkill` | `pgrep -af` then `kill -9` each PID |
| `/health` returning wrong field | format changed, watchdog loops | always include `{ok: <bool>}` |
| Token partially `…` (U+2026) | Hermes env-var redaction | load from file, chmod 600 |
| Auto-reload after provider add | not seeing new provider in `/v1/models` | `fs.watchFile` 2s on DB path, `loadDb()` + `discoverModels()` |
| Stream gets cut at provider timeout | AbortController cancels mid-SSE | use `signal` only on initial connect, drain the body |
| Combo returns same model every call | first-hit cascading is working as designed | don't "fix" this; free providers have very different quotas |
| Provider returns `model: 'wrong-name'` (e.g. `hc/glm-5.3-flash` → `meituan/LongCat-2.0:free`) | new-api front-end remap | accept that and log it; don't try to translate back |

## See also

- `references/routerku-architecture.md` — annotated map of the
  1316-line `router.mjs`, function-by-function.
- `references/provider-catalog-quirks.md` — per-provider notes
  (HCNsec remap, kiro deprecation, free tier limits, etc.) harvested
  from FCC catalog + 9Router live tests.
- `references/9router-db-schema.md` — full SQLite schema for the
  `~/.9router/db/data.sqlite` DB the router reads from.
- `termux-node-projects` — for general Termux/Node patterns
  (DNS, /health, watchdog) that this skill builds on.
- `telegram-bots` — for the token-file / DNS-bypass / kill-pitfall
  patterns the Telegram alert hook depends on.
