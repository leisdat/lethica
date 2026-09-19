---
name: routerku-bai-farm
description: Use when managing routerku + b.ai key-farm on Termux.
---

# routerku + b.ai key-farm integration

## Architecture (verified live)
- **routerku**: `~/routerku/router.mjs` — zero-dep OpenAI-compatible router. Listens on `:20130`. Loads providers/combos/keys from 9Router SQLite at `~/.9router/db/data.sqlite`.
- **b.ai sidecar**: `~/bai-farm/pool-proxy.mjs` — key-pool proxy on `:20131`. 791 keys, models `hy3` + `glm-5.3-flash`, cooldown 60s. Strips `bai/` prefix, forwards to `https://api.b.ai/v1`.
- **watchdog**: supervises routerku + sidecar; sets `RPM_BAI=3000`.
- **9Router DB wiring**: bai provider node (id suffix `f9c7817b`, type `openai-compatible-chat`) has its `baseUrl` rewritten to `http://127.0.0.1:20131` so all `bai/*` traffic routes through the sidecar key-pool.
- **Combos**: `Free-All` and `Free-Kombo` both include `bai/hy3` and `bai/glm-5.3-flash`.

## Quick state check (run after compact — no re-inspection needed)
```bash
# sidecar health
curl -s -m 5 http://127.0.0.1:20131/healthz
echo
# routerku processes
ps aux | grep -E "router.mjs|pool-proxy|watchdog" | grep -v grep | awk '{print $2, $11, $12, $13}'
# reload routerku (re-reads 9Router DB)
curl -s -m 5 -X POST http://127.0.0.1:20130/api/reload
```

## E2E verification (proves combo resolves to sidecar)
```bash
curl -s -m 60 http://127.0.0.1:20130/v1/chat/completions -H 'Content-Type: application/json' \
  -d '{"model":"Free-All","messages":[{"role":"user","content":"reply with exactly: FREEALL-OK"}],"max_tokens":60}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);print('model:',d.get('model'),'| content:',repr(''.join((x.get('delta',{}).get('content','') if 'delta' in x else x.get('message',{}).get('content','')) for x in d.get('choices',[]))))"
# repeat with model: Free-Kombo
```

## Restart stack (if down)
```bash
bash ~/routerku/routerku-watchdog   # or the supervisor script under ~/routerku or ~/bai-farm
```

## DB wiring recipe (bai node -> sidecar)
The bai node lives in `providerNodes` with JSON `data` containing `baseUrl`. Rewrite `baseUrl` to `http://127.0.0.1:20131`, keep `prefix`/`apiType`. Back up the DB first (`cp ~/.9router/db/data.sqlite ~/data.bak-$(date +%s).sqlite`). Then `POST /api/reload`.

## Combo edit recipe
Combos are JSON in `combos.models` (array). Add `"bai/hy3"` / `"bai/glm-5.3-flash"` to `Free-All` / `Free-Kombo`, then `POST /api/reload`. Verify with the E2E curl above.

## Upgrade roadmap (gaps vs current v6.6)
1. Smart/task-aware model selection (static combo -> weighted by latency/cost/task).
2. Adaptive rate learning (static RPM -> learn from 429 Retry-After).
3. Predictive failover (pre-emptive from health EWMA trend, not just post-failure).
4. Multi-farm key aggregation (b.ai + 9Router + routerku free keys in one weighted pool).
5. Per-user auth + quota gateway (API-key, per-key RPM/quota, audit log).
6. Semantic cache (embedding-similarity, not exact-match only).
7. Observability (/metrics Prometheus, request trace-ID).
8. Streaming resilience (SSE resume, mid-stream fallback).
9. Combo auto-builder (top-N free models per category, no hand-edit).
10. Model freshness probe (periodic light call, auto-prune dead models).

## Gotchas
- `/healthz` on sidecar returns `stats.req/ok/dead429/exhausted` — use it as the source of truth for key-pool health.
- routerku caches identical payloads; for burst tests send **unique** prompts or the cache absorbs requests and the sidecar `req` counter won't move.
- If a combo model name is wrong it silently falls through to another model; always E2E-verify the resolved `model` field, not just HTTP 200.
