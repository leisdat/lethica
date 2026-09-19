# 9Router SQLite Schema

`~/.9router/db/data.sqlite` — schema the routerku reads from.

## Tables

### `providerNodes`

One row per upstream API provider.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | format: `openai-compatible-chat-<uuid>` |
| `type` | TEXT | always `openai-compatible` for chat, or `anthropic-messages` for Claude-style |
| `name` | TEXT | display name (e.g. `Api.b.ai`, `Gorouter-main`) |
| `data` | TEXT (JSON) | config blob — see below |
| `createdAt`/`updatedAt` | TEXT | ISO-8601 |

`data` JSON shape:
```json
{
  "prefix": "bai",                        // short id used in /v1/models
  "apiType": "chat",                      // or "responses" for OpenAI Responses
  "baseUrl": "https://api.b.ai/v1",       // upstream base
  "nodeName": "Api.b.ai"                  // for UI
}
```

### `providerConnections`

One or more rows per `providerNodes.id` — each row holds an API key (or
OAuth token) and per-connection settings.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | uuid |
| `provider` | TEXT FK | `providerNodes.id` |
| `authType` | TEXT | `apikey`, `oauth`, `claude-cli`, `kiro-cli` |
| `name` | TEXT | connection display name |
| `email` | TEXT NULL | for OAuth accounts |
| `priority` | INT | lower = tried first in cascade |
| `isActive` | INT 0/1 | inactive = skipped |
| `data` | TEXT (JSON) | key + status |
| `createdAt`/`updatedAt` | TEXT | |

`data` JSON shape:
```json
{
  "apiKey": "sk-...",                   // plaintext OR "enc:v2:<hex>"
  "testStatus": "active",               // active | unavailable | unknown
  "backoffLevel": 0,                    // 0-10, increments on each fail
  "providerSpecificData": {
    "prefix": "bai", "apiType": "chat", "baseUrl": "...",
    "nodeName": "...", "connectionProxyEnabled": false,
    "connectionProxyUrl": "", "connectionNoProxy": ""
  },
  "errorCode": null,
  "lastError": null
}
```

`apiKey` encryption: if the value starts with `enc:`, decrypt with
`ROUTERKU_KEY` env var or `~/.routerku.key` file. Plain `sk-...` keys
are used as-is.

### `combos`

Named groupings of model ids, referenced by name in chat requests.

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | uuid |
| `name` | TEXT UNIQUE | e.g. `Free-Kombo`, `Free-All`, `L` |
| `description` | TEXT NULL | |
| `models` | TEXT (JSON) | array of `prefix/modelId` strings OR combo names (nested) |
| `createdAt`/`updatedAt` | TEXT | |

Nested combos (e.g. `Nycombo` contains `["Free-All", "Free-Kombo", "L"]`):
the router's `resolveCandidates` walks the tree to depth ~5 to avoid
cycles.

### `apiKeys`

Bearer tokens that the router itself accepts (clients must send
`Authorization: Bearer <key>`).

| Column | Type | Notes |
|---|---|---|
| `id` | TEXT PK | uuid |
| `name` | TEXT | display name |
| `key` | TEXT UNIQUE | the bearer secret (e.g. `sk-routerku-...`) |
| `isActive` | INT 0/1 | |
| `createdAt` | TEXT | |

`routerku.authKeys` Set is populated from this table on boot.

## Indexes

None explicitly created in the 9Router schema (relies on JSON extracts
being fast enough for the row counts seen — ~50 providerNodes,
~80 providerConnections).

## Router reads (minimum queries)

```sql
-- providers + their keys
SELECT n.id, json_extract(n.data, '$.prefix') AS prefix,
       json_extract(n.data, '$.baseUrl') AS baseUrl,
       c.id AS conn_id, json_extract(c.data, '$.apiKey') AS api_key,
       json_extract(c.data, '$.providerSpecificData.prefix') AS conn_prefix,
       json_extract(c.data, '$.testStatus') AS test_status,
       c.priority, c.isActive
FROM providerNodes n
LEFT JOIN providerConnections c ON c.provider = n.id
WHERE json_extract(n.data, '$.prefix') IS NOT NULL
  AND c.isActive = 1
ORDER BY c.priority, n.id, c.id;

-- combos
SELECT name, models FROM combos;

-- bearer keys
SELECT key FROM apiKeys WHERE isActive = 1;
```

The router caches these in memory and re-reads when `fs.watchFile` fires
on the DB file (2s interval).

## Insert pattern (for adding a provider from outside the dashboard)

```sql
INSERT INTO providerNodes (id, type, name, data, createdAt, updatedAt)
VALUES (?, 'openai-compatible', ?, ?, ?, ?);

INSERT INTO providerConnections
  (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
VALUES (?, ?, 'apikey', ?, NULL, 1, 1, ?, ?, ?);
```

`data` JSON templates:
- Node: `{"prefix": "<x>", "apiType": "chat", "baseUrl": "https://..."}`
- Connection: `{"apiKey": "<key>", "testStatus": "active",
  "backoffLevel": 0, "providerSpecificData": {...same as node data...}}`

The router's `loadDb()` will pick up the new row on the next 2s tick.

## Marking a connection dead without deleting

```sql
UPDATE providerConnections
SET data = json_set(data,
  '$.testStatus', 'unavailable',
  '$.backoffLevel', 99)
WHERE json_extract(data, '$.providerSpecificData.prefix') = 'xg';
```

The router's `loadDb()` reads `testStatus` and the cascade handler skips
`unavailable` rows. This is reversible (just `json_set` back to
`'active'`).
