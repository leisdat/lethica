# b.ai 791-key farm — sidecar architecture (2026-09-08)

## Topology
```
Hermes / OpenAI-client
   -> routerku :20130  (reads ~/.9router/db/data.sqlite, readOnly)
   -> 9Router node `bai` (baseUrl redirected to sidecar)
   -> sidecar pool-proxy :20131  (~/bai-farm/pool-proxy.mjs)
        - 791 keys loaded from file
        - per-key rotation on 429/402/403
        - honor retry-after
        - strip `bai/` prefix -> forward bare model to https://api.b.ai/v1
   -> api.b.ai upstream
```

## Key facts (verified live)
- Sidecar healthz: `{"keys":791,"dead":0,"available":791,"inflight":N,"req":M}`
- Models exposed by sidecar after strip: `hy3`, `glm-5.3-flash` (routerku shows them as `bai/hy3`, `bai/glm-5.3-flash`)
- Free-All combo final: `bai/hy3`, `bai/glm-5.3-flash` (+ other providers)
- E2E: `bai/hy3` 1.38s OK; burst 40x unique payload -> 40/40 200, 0 exhausted

## Setup / restart procedure
1. Start sidecar: `cd ~/bai-farm && node pool-proxy.mjs` (background). Verify `curl :20131/healthz`.
2. Redirect DB (one-time, backup first):
   ```sql
   -- backup
   cp ~/.9router/db/data.sqlite ~/.9router/db/data.bak-bai-sidecar-$(date +%s).sqlite
   -- point bai node baseUrl to sidecar
   UPDATE providerNodes SET data = json_set(data, '$.baseUrl', 'http://127.0.0.1:20131/v1')
     WHERE name LIKE '%b.ai%';
   ```
3. Ensure watchdog `routerku-watchdog` (pm2) runs — supervises sidecar + sets RPM_BAI=3000.
4. Reload routerku (no restart needed): `curl -X POST http://127.0.0.1:20130/api/reload -H "Authorization: Bearer <apiKey>"`
5. Verify: `curl :20130/health`, `curl :20130/v1/models | grep bai`, then chat test `model=bai/hy3`.

## Pitfalls
- Jangan masukkan 791 key ke `providerConnections` DB — 9Router gak rotate antar key saat 429, sidecar yang pegang rotasi.
- Routerku response cache absorbs identical requests — burst-test pakai payload UNIK (lihat SKILL.md Pitfalls).
- Kalau sidecar mati -> semua `bai/*` 502/timeout. Watchdog restart otomatis; cek `pm2 logs routerku-watchdog`.
