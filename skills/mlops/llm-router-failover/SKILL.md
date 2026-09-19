---
name: llm-router-failover
description: Use when LLM auto-failover won't kick in (9Router combos).
version: 1.0.0
---

# LLM Router Failover (9Router + Genspark + Hermes)

How to make an LLM provider pool fail over automatically when one upstream
exhausts credits or errors — verified end-to-end on the user's Termux setup
(9Router v0.5.55 :20128, Genspark llm_proxy, Hermes).

## The core gotcha: providers return 200 OK with error TEXT, not error codes

The #1 reason "auto-failover doesn't work" is that many providers (Genspark
included) return **HTTP 200** with the error message embedded in
`choices[0].message.content` ("Your Genspark credits have been exhausted...")
instead of an HTTP error status (401/402/429/503). Consequences:

- **Hermes** sees 200 → treats it as a success → fallback chain never triggers.
- **9Router combo runner** sees `b.ok == true` → treats the model as succeeded →
  returns the error text to the user and never tries the next model.
- A 200-with-error also defeats custom error-classifier triggers.

Rule: when debugging "provider gave an error but no failover happened", FIRST
check whether the upstream returned a 200 with the error in the body. Query it
directly and print the raw HTTP status + body.

## 9Router combo semantics (reverse-engineered from build)

9Router stores routing config in `~/.9router/db/data.sqlite` (SQLite). Tables:
`providerNodes` (one per upstream, has `prefix`, `baseUrl`), `providerConnections`
(credentials per provider, incl. custom `openai-compatible-chat-<uuid>` nodes),
`combos`, `apiKeys` (which Bearer keys the router accepts), `kv`.

**A model name is treated as a combo ONLY if a row with that name exists in the
`combos` table AND `kind = 'combo'`.** If `kind` is `NULL`/`None`, the name is
resolved as a plain model list → requesting it routes DIRECTLY (e.g. to the
first model's provider) with **no failover**. Symptom: requesting the combo
name returns the first model's error instead of iterating.

- `kind = 'combo'` → real combo runner: iterates models in list order,
  advances to the next on failure, supports strategies (`fallback`, `fusion`,
  `round-robin`).
- `kind = NULL` → plain list, no iteration.

Fix: `UPDATE combos SET kind='combo' WHERE name='<combo>'` (STOP 9Router first,
see below).

### Combo pitfalls (verified 2026-09-03, routerku v5 / 9Router v0.5.59)

Four distinct "combo looks broken but actually..." failure modes that all
produce 5xx but have different SQL fixes. Always run this audit FIRST when
debugging "combo returns 503/404":

```bash
sqlite3 -separator $'\t' ~/.9router/db/data.sqlite <<'SQL'
.headers on
.mode list
SELECT '-- combos with empty models --' AS audit;
SELECT name, kind, models FROM combos WHERE models IS NULL OR models='[]' OR models='null';
SELECT '-- combos with kind != combo --' AS audit;
SELECT name, kind FROM combos WHERE kind IS NULL OR kind != 'combo';
SELECT '-- prefix in combos but no providerNodes row --' AS audit;
SELECT DISTINCT json_each.value AS bad_prefix
  FROM combos, json_each(combos.models)
 WHERE json_each.value LIKE '%/%'
   AND substr(json_each.value, 1, instr(json_each.value,'/')-1)
       NOT IN (SELECT json_extract(data,'$.prefix') FROM providerNodes);
SQL
```

> If the `sqlite3` CLI is not installed (Termux minimal image), run the same SQL
> via the Python stdlib instead: `python3 -c "import sqlite3; ..."` — fully
> equivalent, verified 2026-09-04.

The four structural classes of breakage and their fix (a fifth — paid models
inside a combo named "free" — is covered below):

1. **Combo `models=[]` (empty array)** — `kind='combo'` but the models list is
   empty. The combo runner resolves to zero candidates → routerku returns
   `503 model_not_found: No available channel for model <name> under group
   <default>`. Auto-reload does NOT fix this; you must write a non-empty array.
   ```sql
   UPDATE combos SET models='["xk/mistralai/mistral-large-2512","bai/deepseek-v4-flash"]' WHERE name='<combo>';
   ```

2. **Combo `kind=NULL`** — name is in the combos table but `kind` column is
   null. Routerku treats it as a flat model list (no iteration, no failover).
   Symptom: first model's error bubbles up directly.
   ```sql
   UPDATE combos SET kind='combo' WHERE name='<combo>' AND kind IS NULL;
   ```

3. **Combo references a prefix with no `providerNodes` row** — model like
   `oc/big-pickle` where prefix `oc` was never added (or was added without a
   matching `providerConnections` row → see #4). Routerku skips the candidate,
   tries the next; if ALL candidates have a missing prefix, you get
   `404 unknown provider: <prefix>` in the final error. Fix is to either:
   - add the node + connection (see "Adding a provider" below), or
   - replace the model in the combo with a valid `prefix/model` from an
     existing node (use `SELECT name FROM providerNodes` to pick one).

4. **`providerNodes` row exists but NO `providerConnections` row** — routerku's
   `loadDb` filters nodes by `connections.length > 0` (it skips orphaned nodes
   even if `isActive=1` on the node). This is the most common silent failure
   when patching the DB. Symptom: node appears in `SELECT * FROM providerNodes`
   but `/v1/models` does not list any model under that prefix, and combos that
   reference it get `404 unknown provider`. Auto-reload (watchFile 2s) WILL
   re-pick up a freshly added connection, so you don't need to restart the
   server — just add the connection row and wait ~3s.

   Audit:
   ```sql
   SELECT pn.id, pn.name
     FROM providerNodes pn
     LEFT JOIN providerConnections pc ON pc.provider=pn.id
    GROUP BY pn.id
   HAVING COUNT(pc.id)=0;
   ```

   Fix: insert a `providerConnections` row with `provider=<node.id>` and an
   `apikey` `data` payload (see "Adding a provider" recipe below).

### Failure class #5: a combo named "free" contains PAID models (verified 2026-09-04)

Symptom: user requests combo `Free-Kombo` → `HTTP 400: credit insufficient
balance: balance=7520 required=91146` → Hermes surfaces "Billing or credits
exhausted". The combo NAME promises free; the CONTENT doesn't. `required=91146`
was Claude-Opus-class pricing on a pay-as-you-go upstream (`tabi/claude-opus-5`)
which can never succeed on a low-balance account; its sibling
`tabi/claude-opus-5-thinking` returned `model_not_found` (channel delisted).

Triage recipe (no guessing):
1. Read the combo's `models` JSON from the `combos` table.
2. Check each prefix's connection health straight from the DB —
   `providerConnections.data` JSON carries `testStatus` (`active`/`unavailable`),
   `errorCode` (e.g. 429), `backoffLevel`. A prefix with
   `testStatus=unavailable` is dead regardless of combo naming.
3. Live-probe every candidate model through the router (`max_tokens:5`) and keep
   ONLY the ones that actually answer. Then `UPDATE combos SET models='[...verified...]'`.
4. Verify by requesting the COMBO NAME and checking the response's `model` field
   — it shows which candidate failover landed on (proves iteration works, not
   just that one model answers). A first-prefixed provider may be in cooldown
   from the probe loop itself; failover sliding past it is the pass condition.

Probe matrix + provider verdicts from this repair: `references/free-provider-probe.md`.

### Combo name resolving through nested combos — when a parent combo
references another combo by NAME (not as `prefix/model`), the inner combo is
fully expanded. If the inner combo is `[]` (class #1 above), the parent
silently loses those candidates — no error, just a smaller pool. Always make
sure every combo referenced by name has a non-empty `models` array.

Debug: `sqlite3 ~/.9router/db/data.sqlite "SELECT name, models FROM combos"`
should show non-empty `models` for every combo you reference, directly or
transitively.

## Combo runner billing-text detection (manual patch, re-apply on update)

Even with `kind='combo'`, the combo runner's success check is `if(b.ok)return b`
— a 200-with-error-text still short-circuits. Patch the compiled combo runner to
treat billing text inside a 200 as a failure so it advances:

- File: `/data/data/com.termux/files/usr/lib/node_modules/9router/app/.next-cli-build/server/chunks/8910.js`
- Location: inside `q()` (the combo runner), the `if(b.ok)return ...` branch in the model loop.
- Pattern to detect (lowercased body): `credit`+`exhaust` together, OR
  `insufficient_quota`, OR `billing_error`. Use `b.clone().text()` (NOT
  `.json()`) so it works on both JSON and SSE bodies.
- **Backup before patching** (`cp 8910.js ~/.9router-backup-8910.js`). A bad
  replace that introduces a literal `\n` in the minified file → SyntaxError.
- **The patch is manual and LOST on 9Router update** — keep the backup, and
  re-apply after any upgrade/rebuild (`cleanDistDir` is true, but a running
  server reads the chunk file on boot, so a restart after patch is required).
- Verify: request the combo with the exhausted provider first; it should skip
  it and answer from a working provider (test directly with curl + Bearer key,
  and separately through Hermes).

## Adding a provider to 9Router (recipe)

1. **STOP 9Router first** — editing the DB while it runs can be overwritten or
   locked. Kill the **child node process**, not just the bash wrapper:
   ```bash
   PID=$(pgrep -f "9router -n" | head -1)
   [ -n "$PID" ] && kill -9 $PID
   # Verify: pgrep -af "9router -n" | grep -v "bash -c" || echo "mati"
   ```
   Wrapper-only kills leave the node child alive serving stale state. The child
   PID is the one shown by `pgrep -af "9router -n" | grep -v "bash -c"`.

   Scope note: the stop-first caution applies to the 9Router Next.js server.
   Combo `UPDATE`s against the shared DB while **routerku (:20130)** is running
   are safe — its watchFile reloads within ~4s, no restart needed (verified
   2026-09-04: Free-Kombo rebuilt live, combo answered on next request).

2. **Add the upstream's key** to `apiKeys` table (that's the key the router
   accepts — a "personal" key for the router plus the provider key both work).

3. **Insert `providerNodes` row** — custom OpenAI-compatible endpoints use
   type `openai-compatible` with an auto-generated UUID id:
   ```sql
   -- node_id = "openai-compatible-chat-" + uuid
   INSERT INTO providerNodes (id, type, name, data, createdAt, updatedAt)
   VALUES (?, 'openai-compatible', '<Name>',
           '{"prefix":"<prefix>","apiType":"chat","baseUrl":"<base_url>"}',
           '<now>', '<now>');
   ```
   **Critical**: the `data` JSON column must have `prefix` at the top level
   (`{"prefix":"myt",...}`). The resolver does `find(a=>a.prefix===providerAlias)`
   — it reads `a.prefix`, NOT `a.data.prefix`. The mapper function `g()` in
   the runtime spreads parsed JSON fields into the object top-level, so the
   prefix must be a top-level key of the JSON string.

4. **Insert `providerConnections` row** with credentials in `data` JSON:
   ```sql
   INSERT INTO providerConnections
     (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
   VALUES (?, ?, 'apikey', ?, NULL, 1, 1, ?, '<now>', '<now>');
   ```
   - `provider` field = **node ID** (the `openai-compatible-chat-<uuid>`), NOT
     the prefix string.
   - `data` JSON MUST include `providerSpecificData` with the same prefix,
     nodeName, and proxy config:
     ```json
     {
       "apiKey": "<upstream-key>",
       "testStatus": "active",
       "providerSpecificData": {
         "prefix": "<prefix>",
         "apiType": "chat",
         "baseUrl": "<base_url>",
         "nodeName": "<Name>",
         "connectionProxyEnabled": false,
         "connectionProxyUrl": "",
         "connectionNoProxy": ""
       },
       "errorCode": null,
       "backoffLevel": 0
     }
     ```

5. **The double-prefix trick** — some upstream APIs (e.g. tokenin.my.id)
   require the model name INCLUDE the provider prefix (e.g. `myt/gpt-5-mini`).
   9Router normally strips the first prefix before forwarding: `myt/gpt-5-mini`
   → upstream receives `gpt-5-mini`. If the upstream rejects that, register
   models with a **double prefix**: `myt/myt/gpt-5-mini` → 9Router strips one
   `myt/` → forwards `myt/gpt-5-mini` → upstream accepts. Add these to a
   combo's `models` JSON array as `"myt/myt/gemini-3.5-flash-free"`.

6. **(Optional) Add models to a combo** — prepend models to the `combos` row's
   `models` JSON array. Order = priority, so best/cheapest first. Use `UPDATE`
   with `STOP` first.

7. **Restart 9Router**, then verify:
   ```bash
   # Check models appear
   curl -s http://127.0.0.1:20128/v1/models | python3 -c "import json,sys; ms=json.load(sys.stdin)['data']; print([m['id'] for m in ms if 'myt/' in m['id']][:5])"
   # Test a direct model call
   curl -s http://127.0.0.1:20128/v1/chat/completions \
     -H "Authorization: Bearer <router-key>" \
     -H "Content-Type: application/json" \
     -d '{"model":"<prefix>/<model>","messages":[{"role":"user","content":"hi"}],"max_tokens":20}'
   ```

## Wiring Hermes to the router

- `hermes config set model.base_url "http://127.0.0.1:20128/v1"` — the trailing
  **`/v1` is REQUIRED** or Hermes 404s (it appends `/chat/completions`).
- `hermes config set model.default "<combo-name>"` (e.g. `Free-All`) +
  `model.provider custom` + `model.api_key <router-key>`. The combo name IS the
  model — the router then owns failover, so Hermes fallback chain is not needed.

### "Provider authentication failed" (Hermes → router) — root cause & fix

Symptom: chat replies "⚠️ Provider authentication failed. Check the configured
credentials; raw provider details are in the gateway logs." while the router
itself answers fine on direct curl.

Root cause #1 — `model.api_key` in `~/.hermes/config.yaml` points at a **stale
env var from a previous provider**. Hermes builds the env-var name from
`base_url` host+port with dots→underscores: for
`http://127.0.0.1:20128/v1` the var is
`HERMES_CUSTOM_127_0_0_1_20128_API_KEY`, defined in `~/.hermes/.env`. If the
base_url changed (e.g. 9Router → routerku) but api_key still references the old
var (`HERMES_CUSTOM_ZENMUX_AI_API_KEY`), the value resolves empty → 401 → this
error. Fix: `hermes config set model.api_key '${HERMES_CUSTOM_127_0_0_1_20128_API_KEY}'`.

Root cause #2 — `/model` picker (Telegram inline keyboard) offers BOTH
`Local (127.0.0.1:20128)` AND `Local (localhost:20128)` — these map to
DIFFERENT env vars (`HERMES_CUSTOM_127_0_0_1_...` vs `HERMES_CUSTOM_LOCALHOST_...`).
Only the 127.0.0.1 form is populated in `.env`, so choosing `localhost` yields
a missing var → auth failed. Always pick the `127.0.0.1` entry.

Debug in 2 steps: (1) curl the router's `/v1/models` + `/v1/chat/completions`
directly with the key from `.env` — a 200 means the router is healthy and the
problem is Hermes-side config; (2) `grep -A5 "^model:" ~/.hermes/config.yaml`
and confirm `api_key` references an env var that actually exists in `.env`.
After fixing, re-pick the model via `/model` — a stale session override
("Rehydrated persisted /model override" in logs) can otherwise keep using the
old model/provider.

- Aliases (`model.aliases`) are `provider/model` strings; a bare `custom/x`
  uses the current custom provider's base_url. For per-alias base_url use the
  full `model_aliases:` dict form (model, provider, base_url) — `api_key_env`
  in that form is NOT read by DirectAlias resolution (only model/provider/base_url).
- When 9Router requires auth on the incoming key, its API keys are in the
  `apiKeys` table — add Hermes's key there or the router returns
  `401 invalid_api_key`.

## Chaining two routers = double strip = need DOUBLE prefix (verified 2026-08-30)

Routerku (:20130) reading the same 9Router DB but running as its own server: when a
combo model routes **routerku → 9Router → upstream**, BOTH routers strip one prefix.
`gcli/grok-4.6` → routerku strips `gcli/` → forwards `grok-4.6` → 9Router has no prefix
to route on → `404 unknown provider` / `No active credentials for provider: openai`.

Fix: register the OAuth-only provider (`gcli`=grok-cli, `kr`=kiro) in routerku's DB as
an OpenAI-compatible node whose `baseUrl` = **9Router local** (`http://127.0.0.1:20128/v1`),
and make the combo use a **double prefix**: `gcli/gcli/grok-4.6` → routerku strips 1 →
9Router receives `gcli/grok-4.6` → routes correctly.

- Symptom to recognize: `404 All providers failed. Last: unknown provider: gcli` from
  routerku = provider prefix missing from its `providerNodes` (OAuth connections only
  carry `accessToken`, not `apiKey` — routerku's `loadDb` skips them).
- Model discovery for these can show `0 models` (9Router needs >6s to list 1437 models)
  yet **request forwarding still works** — discovery only feeds `/v1/models` listing.
- Detail: see skill `9router-providers` (OAuth provider pitfall) and `routerku` (register
  provider via 9Router upstream).

## Verification checklist

- Direct curl to router `/v1/chat/completions` with `model=<combo>` answers from
  a NON-exhausted provider (SSE: parse `data:` lines).
- `hermes chat -q "..."` answers (end-to-end through the router).
- `hermes config get model` shows base_url with `/v1`.
- Combo row `kind='combo'` for any name you want failover on.
- **Combo audit SQL (above) returns 0 rows** before declaring a fix complete.
- **Direct upstream probe** for every prefix used in combos returns models:
  `curl -H "Authorization: Bearer <key>" https://<baseUrl>/v1/models | jq '.data[].id'`
  — confirms the prefix's baseUrl still hosts the models you reference.

## Router cache pitfall: combo calls may STICK to one model (verified 2026-09-04)

routerku (and 9Router) caches the resolved model per combo per session — first
successful hit is sticky for subsequent calls. Symptoms of a working failover
that *looks* broken:

- `POST /v1/chat/completions {"model":"Free-All"}` returns `minimax-m3:free`
  nine times in a row even after you added `claude-opus-5` to position 1.
- `Free-All` rotation shows 1 model, not the 5+ in the array.
- New model feels "ignored" / "dead" because cascade never reaches it.

**Why**: round-robin first-hit, plus routerku's `providerStats[prefix]` for
cooldown / RPM / RPD. The first candidate that returned 200 becomes the
session's default until upstream cool-down. New models only appear in the
rotation AFTER the current favorite errors (402/429/timeout) and the
failover actually advances.

**Workaround for verification (do this when confirming a new model in a combo)**:

1. **Direct prefix call**, not combo — bypass cache entirely:
   ```python
   for m in ("gr/claude-opus-5", "rk/glm-5.2", "hc/MiniMax-M3"):
       body = json.dumps({"model":m,"messages":[{"role":"user","content":"OK"}],"max_tokens":4}).encode()
       req = urllib.request.Request("http://127.0.0.1:20130/v1/chat/completions", data=body,
           headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"})
       r = json.loads(urllib.request.urlopen(req, timeout=60).read())
       print(m, "→", r.get("model"))   # should print upstream model id, not the prefix/m you sent
   ```
2. **Send N requests in a row** and look for rotation across the N responses
   (only works if no candidate is in cooldown):
   ```python
   seen = []
   for _ in range(10):
       seen.append(call("Free-Kombo").get("model"))
   print(set(seen))  # if length 1 → cache is stuck, NOT a real failover test
   ```
3. **Force failover** by giving the sticky model a deliberate cooldown (set
   its `backoffLevel` high in `providerConnections.data`) and re-request.
4. **Re-test in a fresh session** if you really want cold-cache behavior
   (the in-memory cache lives in the router process; pm2 restart resets it).

**Implication for triage**: never judge "model X is dead" by combo response
alone. Always do a direct `prefix/model` call to know the truth, and trust
`response.model` (the upstream's actual model id) over the request's `model`
field (which the router may rewrite on double-prefix).

## Combo prune without deleting (mark unavailable, keep row) (verified 2026-09-04)

When cleaning a bloated combo, you have two strategies. Prefer MARK over
DELETE — node/connection rows hold keys and config that are painful to
rebuild. DELETE only when the key is provably revoked or the upstream is
permanently dead.

**Mark** (preserves everything, makes the row instantly skipped):
```python
import sqlite3, json
db = os.path.expanduser("~/.9router/db/data.sqlite")
c = sqlite3.connect(db).cursor()
# Backoff 99 = max skip; testStatus=unavailable = excluded from active list
c.execute("""UPDATE providerConnections
  SET data = json_set(data, '$.testStatus', 'unavailable', '$.backoffLevel', 99)
  WHERE json_extract(data, '$.providerSpecificData.prefix') = ?""", ("xg",))
```
Restart not required for routerku (watches DB). After marking, any combo that
referenced `xg/*` will fail to resolve it and fall through to the next
candidate. Re-enable later by `json_set(data, '$.testStatus', 'active',
'$.backoffLevel', 0)`.

**Delete** (only when key is provably dead — e.g. 401 invalid_api_key, 403
revoked, or upstream domain gone):
```python
c.execute("DELETE FROM providerConnections WHERE name = ?", ("old-key",))
c.execute("DELETE FROM providerNodes WHERE name = ?", ("OldProvider",))
```
DELETE from `providerConnections` is the lighter option (just unlinks a key);
DELETE from `providerNodes` removes the whole prefix — combo entries that
referenced it will become silently dead (failure mode #3 in combo pitfalls).

## Stale 9Router Next.js on :20128 vs routerku on :20130

After upgrading 9Router or running its dev server, a **Next.js production
server can linger on :20128** while routerku owns :20130. The two are easy to
mix up — Hermes is wired to one but logs reference the other. Diagnose with:

```bash
ss -tlnp 2>/dev/null | grep -E ':2012[89]|:20130' \
  || netstat -tlnp 2>/dev/null | grep -E ':2012[89]|:20130'
pgrep -af 'next-server\|router\.mjs' | grep -v 'bash -c'
```

- Port `:20128` with a Next.js server: `/v1/models` returns 200 with the full
  1437-model catalog, but `/v1/chat/completions` returns **405 Method Not
  Allowed** (Next.js serves models as a static route, not the chat API).
- Port `:20130` with routerku: both endpoints work, combos resolve correctly.

When a Next.js instance is still bound to `:20128` and you want only routerku
serving traffic, kill the leftover before starting routerku on the same port
or vice versa:

```bash
pkill -9 -f 'next-server\|9router' && sleep 1 \
  && pgrep -af 'next-server\|9router' | grep -v 'bash -c' || echo 'clean'
# Then in foreground, start routerku:
cd ~/routerku && node router.mjs
# (use background=true in Hermes terminal; bare `&` in foreground is rejected)
```

Important terminal tool quirk: do **NOT** use `&` for backgrounding in a
foreground terminal call — Hermes rejects it and tells you to re-send with
`background=true` (which gives you a `session_id` + `pid`). Use
`background=true` for any long-lived server; reserve `notify=true` for
bounded jobs.

See `references/genspark-9router-setup.md` for the exact commands used when
adding Genspark (53 models, prefix `gs/`, Free-All combo with 86 models across
8 providers) and the Hermes alias set. See `references/tokenin-provider.md`
for a concrete example of adding a provider whose API requires the prefix in
model names (the double-prefix trick). See `references/free-provider-probe.md`
for the free-vs-paid probe matrix (401 vs insufficient_quota vs
model_not_found vs cooldown) and the 2026-09-04 Free-Kombo repair walkthrough.
See `references/provider-catalog-mining.md` for sourcing NEW free upstreams:
mining an open-source router's provider catalog (FCC pattern), matching idle
`~/.hermes/.env` keys to catalog base URLs, new-api / Cloudflare-1010 / SNI
error fingerprints, and the "models list is not proof — chat-test" rule.