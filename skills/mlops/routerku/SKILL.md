---
name: routerku
description: Use when running/building routerku, the zero-dep LLM router.
version: 1.0.0
author: letticha
license: MIT
metadata:
  hermes:
    tags: [llm, router, 9router, proxy, termux]
    related_skills: [9router, llm-router-failover]
---

# Routerku — minimal zero-dep LLM router (Termux)

## When to Use

Pakai skill ini kalau: (1) mau start/restart routerku di ~/routerku/router.mjs, (2) debug kenapa routerku gak nyambung/gagal, (3) tambah fitur ke routerku, atau (4) mau paham cara resolve/failover/cooldown routerku bekerja.

Custom LLM router di `~/routerku/router.mjs` — **1 file, ZERO dependency** (cuma `node:http` + `node:sqlite` built-in Node 22.13+). Gak perlu `npm install`. Baca langsung dari DB 9Router (`~/.9router/db/data.sqlite`) jadi semua provider/combo/key otomatis kepake tanpa input ulang.

## Run & config

```bash
node ~/routerku/router.mjs            # start (background=true di Hermes)
ROUTERKU_PORT=20130 node ~/routerku/router.mjs   # ganti port (default 20130)
ROUTERKU_DB=/path/data.sqlite ...     # ganti DB source
ROUTERKU_TIMEOUT=45000                # timeout upstream ms
```

Port 20130 sengaja — 9Router :20128, NOVA :3001, FreeLLMAPI :3002 semua beda.

## Endpoint

- `GET /health` — tanpa auth, nunjukin providers/combos/uptime
- `GET /v1/models` — auth: `auto` + semua combo + `prefix/*`
- `POST /v1/chat/completions` — auth, support stream (SSE pass-through)

Auth: bearer key dari tabel `apiKeys` 9Router (isActive=1) — pake key yang sama kayak 9Router, gak perlu bikin baru.

## Resolve model (urutan)

1. `auto` / kosong → semua provider diurut priority, failover otomatis
2. nama = combo (`Free-All`, `Nycombo`, dll) → **nested combo di-expand rekursif** (cycle guard), failover antar model
3. `prefix/model` → langsung ke provider itu
4. nama bare (`deepseek-v4-flash`) → coba semua provider

## Failover & cooldown

- Gagal (402/403/429/5xx/timeout/billing-text) → coba kandidat berikutnya, catat cooldown per prefix:
  - 429 → 60s
  - billing-text dalam 200 (credit exhaust / insufficient_quota / billing_error) → 30 menit (1800s)
  - 5xx → 15s
  - lainnya → 5s
- Prefix ganda tetap didukung: `myt/myt/model` → strip 1 prefix → forward `myt/model` (sama kayak 9Router).
- Upstream URL: `baseUrl` dari `providerNodes.data` (jangan lupa strip trailing `/`), strip 1 prefix sebelum forward.

## Debug

Log route ke stdout: `[try] prefix → model`, `[fail] prefix status=..`, `[ok] prefix (KB)`, `[cooldown] prefix +Ns`. Cek via `process(action='log')` kalau jalan background.

## Provider: tokenrouter (prefix `tr`, 2026-08-29)

- Endpoint: `https://api.tokenrouter.com/v1`, 131 model — model ber-prefix (`z-ai/*`, `openai/*`, `google/*`, `nvidia/*`, `qwen/*`...).
- **Double-prefix**: `tr/z-ai/glm-5.3-free` → strip 1 → forward `z-ai/glm-5.3-free` → upstream terima. Verifikasi: 9.3s, model `glm-5.3`, balas `oke`.
- **Free yang beneran jalan cuma `z-ai/glm-5.3-free`**. `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` ada di list tapi 403 "insufficient_user_quota" (label free tapi butuh saldo) — SKIP.
- Key `sk_OzWm...` di providerConnections.
- Sudah masuk Free-All posisi 4.

## Provider: zanslab (prefix `zl`, 2026-08-29)

- Endpoint: `https://zanslab.id/v1`, 26 model — semuanya model ber-prefix: `an/*` (Claude), `op/*` (GPT), `go/*` (Gemini), `zai/glm-5.2`, `de/*`, `mm/mimo-v2.5`.
- **Karena upstream list model ber-prefix, routerku expose double-prefix**: `zl/zai/glm-5.2` → strip 1 `zl/` → forward `zai/glm-5.2` → upstream terima. Verifikasi: `zl/zai/glm-5.2` → model `glm-5p2`, 2s.
- Key `sk_9r_live_...` disimpan di providerConnections (tidak di-hardcode di skill).
- Sudah masuk Free-All combo di posisi 3 (setelah bai). Kalau bai 403/limit, glm-5.2 kepake.

## Provider: B.AI (prefix `bai`, 2026-09-01)

- Endpoint: `https://api.b.ai/v1`, model `bai/deepseek-v4-flash` dll.
- **Multi-key stacking**: tambah key baru via DB 9Router (`providerConnections`) dengan `isActive=1` + `priority` lebih tinggi. Routerku auto-load semua key aktif & rotate saat 402/403.
- **PITFALL "Invalid API key" via routerku tapi key valid langsung ke upstream**:
  - Kalau test via routerku balas `Invalid API key` tapi `curl` langsung ke `https://api.b.ai/v1/chat/completions` pakai key yang sama **works** → masalahnya **key lama (priority 1) yang dipakai duluan tapi sebenarnya expired**, bukan routerku yang salah.
  - Verifikasi: cek `[try] bai → bai/deepseek-v4-flash attempt=1 key=...` di log routerku — kalau key=1 (lama) yang dipakai, rotasi key atau update priority.
  - **Auth key routerku** (client key, bukan upstream key) — test pakai auth key dari tabel `apiKeys` 9Router yang `isActive=1` (bukan asal key, kalau salah balas `Invalid API key` juga).
  - Key lama tetap ada di DB (aktif) tapi expired — cek `providerConnections` di `~/.9router/db/data.sqlite`, rotasi `priority` atau set `isActive=0`.

### Production: b.ai 791-key farm via sidecar (2026-09-08)

Skala ratusan key (farm) **gak** di-handle via DB-priority (terlalu banyak baris + 9Router gak rotate antar key saat 429). Solusi terverifikasi: **sidecar pool-proxy** yang pegang semua key, lalu DB `bai` node di-redirect ke sidecar.

- Sidecar `~/bai-farm/pool-proxy.mjs` jalan di **:20131** — load 791 key dari file, rotasi per-key saat 429/402/403, hormati `retry-after`, **strip prefix `bai/`** sebelum forward ke `https://api.b.ai/v1` (upstream b.ai pakai bare model name). Expose `/v1/chat/completions`, `/v1/models`, `/healthz` (payload: `keys/dead/available/inflight/req`).
- **Integrasi routerku**: redirect `baseUrl` node `bai` di `~/.9router/db/data.sqlite` → `http://127.0.0.1:20131/v1` (backup DB dulu). Routerku baca DB → resolve `bai/hy3` → 9Router-bai-node → sidecar → b.ai. Jadi 791 key dipakai tanpa masuk ke DB.
  - Verifikasi: `SELECT data FROM providerNodes WHERE name LIKE '%b.ai%'` → `baseUrl` harus `http://127.0.0.1:20131/v1`.
- **Watchdog** `~/bai-farm/routerku-watchdog` (bash, jalan via pm2 `routerku-watchdog` — beda proses dari pm2 `routerku`) supervise sidecar + set `RPM_BAI=3000` lewat env, restart sidecar kalau mati.
- **Reload tanpa restart**: `POST http://127.0.0.1:20130/api/reload` (auth) → routerku re-read DB + discovery. Bukti: 28 providers, 1454 models.
- **Combo free**: pastikan `Free-All`/`Free-Kombo` isinya `bai/hy3` + `bai/glm-5.3-flash` (alias dari sidecar, BUKAN model `bai/*` lama yang mati). Cek `SELECT models FROM combos WHERE name='Free-All'` setelah reload.
- Detail arsitektur + cara restart: `references/bai-sidecar.md`.

## Model discovery

Routerku otomatis fetch `/v1/models` dari tiap provider saat startup (parallel, 6s timeout per provider). Hasilnya di-expose di `/v1/models` sebagai `prefix/model` — contoh: `bai/minimax-m3`, `or/qwen/qwen3.8-flash`, `myt/myt/gpt-5-mini` (double-prefix untuk upstream yang list prefixed).

Discovery dijalankan SEBELUM listen, jadi /v1/models langsung siap saat server nyala. Restart untuk refresh.

## Warisan dari 9Router

Routerku baca langsung dari DB 9Router (`~/.9router/db/data.sqlite`). Artinya:
- Provider + key + combo diwariskan otomatis — gak perlu input ulang
- 9Router bisa dimatiin (DB tetap ada, routerku baca read-only)
- Kalau mau tambah provider, masih bisa via 9Router (start 9Router, tambah, restart routerku), atau langsung edit DB

## Pitfalls

- **Provider dengan saldo habis** — 402/403 dari upstream bukan bug router, cek saldo provider.
- **Burst test ke-absorb response cache** — routerku response cache (v6, default ON) menjawab request NON-STREAM identik dari cache, jadi burst 30x payload SAMA cuma hit upstream 1x (counter `req` sidecar cuma +10). Untuk tes rotasi key beneran, **kirim payload UNIK** (beda message/nonce) — baru semua tembus upstream. Bukti: 40x payload unik → 40/40 200, sidecar req +40, 0 dead429. Matikan cache sementara pakai body `{"cache":false}` atau env `ROUTERKU_RESP_CACHE=0` kalau mau tiap request tembus.
- **Double-prefix** — upstream tokenin (`myt`) list model dengan prefix `myt/...`, routerku expose `myt/myt/...` biar strip-1 nyisain prefix. Contoh: `myt/myt/gpt-5-mini` → strip "myt/" → forward `myt/gpt-5-mini` → tokenin terima.

- **Nested combo butuh resolveCandidates rekursif** (Nycombo berisi nama combo lain). Kalau liat `unknown provider: <nama-combo>` → combo di dalem combo belum di-expand.
- **Content kosong bukan error** — model reasoning (deepseek dll) bisa habisin `max_tokens` kecil buat `reasoning_content`, content jadinya `''`/null. Naikin max_tokens atau jangan judge gagal.
- Kalau edit file → restart proses (kill + start ulang).
- Zero-dep berarti `node:sqlite` harus ada: butuh Node >= 22.13 (di Termux pakai `nodejs-lts` atau v24).

## Fitur v3: circuit breaker + rate limit + retry + models cache (2026-08-30)

**Status: AKTIF ✅** — dashboard redesain v3, backend v3.

### Circuit Breaker
- 3x gagal beruntun dalam 5 menit → `OPEN` (skip 5 menit) → `HALF_OPEN` (boleh 1 probe) → sukses = `CLOSED`, gagal = `OPEN` lagi.
- Cooldown lama tetap jalan paralel: 429→60s, billing→30m, 5xx→15s, lainnya→5s.
- Reset manual: `POST /api/circuit/reset` (auth) atau tombol "Reset Circuit" di dashboard.

### Rate Limit (RPM/RPD)
- Per-prefix: default 60 RPM / 5000 RPD (env `ROUTERKU_RPM`, `ROUTERKU_RPD`).
- Rolling window 60s / 24h, skip candidate kalau kena limit.
- `/api/status` nampilin `rateLimits` + `circuitBreaker` state per provider.

### Retry
- Error retryable (429/5xx/timeout) → 1x retry dengan delay 1s sebelum pindah provider.
- Billing-text dalam 200 / 402/403 → gak di-retry, langsung failover.

### Models cache
- List model disimpan ke `~/.routerku-models.json` (valid 1 jam).
- Startup: kalau cache fresh → langsung pakai + re-discover di background.
- Health check & discovery tetap jalan seperti biasa.

### Dashboard v3
- Hero header + 4 stat card, provider card dengan circuit state badge, tabel analytics + kolom Circuit, log dengan filter (Semua/OK/FAIL), tombol Reset Circuit.
- File: `~/routerku/dashboard.html` (dibaca server tiap request — edit langsung, gak perlu restart).

## Fitur v5: auto-compact + cumulative token tracking (2026-08-30)

**Status: AKTIF ✅**

### Auto-compact (cegah ngeloop)
- Estimasi token dari `messages` (heuristik chars/4), kalau melebihi `ROUTERKU_MAX_INPUT_TOKENS` (default 100000) → pangkas ke **head** (semua pesan system + user pertama) + **tail** (N pesan terakhir, `ROUTERKU_COMPACT_KEEP` default 12), sisipkan note sistem "[Auto-compact: ...]".
- Mutate `messages` in-place, berlaku SEKALI per request (flag `__compactApplied`).
- Set `ROUTERKU_MAX_INPUT_TOKENS=0` → nonaktif.
- Test: threshold 50 → compactCount naik (verified).
- **PITFALL**: threshold kecil (mis. 50) di percakapan nyata → SEMUA pesan di luar head/tail ke-pangkas → model lupa konteks. Default 100000 aman untuk request normal; kalau mau agresif turunkan ke 30000-50000.

### Cumulative token tracking
- `trackTokens()` — tambah prompt/completion ke `providerStats[prefix]` DAN `cumulativeTokens` global `{in, out, compactCount}`.
- `logRequest` pakai `trackTokens` (refactor dari inline).
- `/api/stats` nambah `cumulativeTokens`.
- Dashboard: stat card "Total Input Tokens", "Total Output Tokens", "Auto-compact" (format id-ID).

### Restart wajib pakai pm2 (JANGAN delete!)
- `pm2 restart routerku` — env override bisa lewat `pm2 start router.mjs --name routerku --update-env` atau env inline.
- **JANGAN `pm2 delete routerku`** — tidak ada ecosystem.config.cjs di ~/routerku; delete = routerku mati permanen sampai di-start ulang manual.
- Kalau test auto-compact pake env inline (`ROUTERKU_MAX_INPUT_TOKENS=50 pm2 restart ...`), env-nya NYANGKUT di pm2 — wajib `pm2 delete` + `pm2 start` bersih biar balik ke default 100000/12.

### PITFALL Uint8Array stream chunk
- `for await (const chunk of result.stream)` — chunk itu **Uint8Array**. `chunk.toString()` = `"4,101,100,..."` (byte CSV), BUKAN teks! Jadi `chunk.includes('"usage"')` gak pernah match → token streaming gak ke-track (bug yang bikin `/api/stats` kosong).
- **Fix: `Buffer.from(chunk).toString('utf8')`** — verified: setelah fix, `[ok] bai stream done tokens:24`.
- Parse usage streaming pakai `extractUsageFromSSE(tailBuf)` — scan baris `data: {...}` dari belakang, JSON.parse penuh (regex `[^}]*` gagal krn nested object `prompt_tokens_details` dll).

## Fitur v4: multi-key rotation + persistent log + token tracking + per-provider RPM/RPD + API key management (2026-08-30)

**Status: AKTIF ✅**

### Multi-key rotation
- Provider bisa punya multiple keys (dari `providerConnections` dengan `isActive=1`, diurutin `priority`).
- Kalau key kena 402/403/billing-text → auto-rotate ke key berikutnya (gak burn retry attempt).
- `/api/status` nampilin `keyCount` + `activeKey` per provider.
- Provider dengan multi-key: cag(3), kiro(3), qoder(3), xai(2), openrouter(2), tokenrouter(2).

### Persistent log
- Setiap request di-append ke `~/.routerku-requests.log` (JSON lines).
- `GET /api/log?n=200` (auth) — baca log persistent (max 2000 entries).
- `POST /api/stats/clear` sekarang juga truncate file log.
- Log in-memory (200 entries) tetap dipake buat dashboard real-time.

### Token tracking
- Parse `usage` field dari upstream response (`prompt_tokens`, `completion_tokens`, `total_tokens`).
- `/api/stats` nampilin `tokens: { prefix: { in, out } }`.
- Dashboard tabel analytics bisa nunjukin token consumption.

### Per-provider RPM/RPD
- Default 60 RPM / 5000 RPD per provider.
- Override per-prefix via env: `ROUTERKU_RPM_BAI=120`, `ROUTERKU_RPD_ZL=3000`.
- Rolling window 60s / 24h, skip otomatis kalau kena limit.

### API Key Management
- `GET /api/keys` (auth) — list semua API key (tanpa nilai key, cuma id/name/isActive/createdAt).
- `POST /api/keys` (auth) — add key baru: `{ "key": "sk-...", "name": "Label" }`.
- `DELETE /api/keys/:id` (auth) — hapus key.
- Setelah add/delete, auth keys auto-reload (gak perlu restart).

## Fitur v2: AES-256-GCM key encryption (2026-08-30)

**Status: AKTIF ✅** — key upstream di-encrypt AES-256-GCM di memori, gak pernah plaintext.

### Cara kerja
- Master key: dari env `ROUTERKU_MASTER_KEY` (32-byte hex/base64) ATAU auto-generate `~/.routerku-master.key` (chmod 600, 32 byte random).
- Saat `loadDb()`: key dari `providerConnections.data.apiKey` langsung di-encrypt (`encryptKey()`) → simpan sebagai `prov._encKey`. `prov.key = null` (gak ada plaintext).
- Saat request upstream: `getDecryptedKey(prov)` → `decryptKey(prov._encKey)` → plaintext cuma ada sebentar buat header `Authorization: Bearer ...`.
- 4 titik pemakaian key: `discoverModels`, `callUpstream`, `checkProviderHealth`, dan `authKeys` (client key, gak di-encrypt — itu bukan upstream key).
- Backward compat: kalau `prov._encKey` gak ada, fallback ke `prov.key` (plaintext). Kalau decrypt gagal (wrong master key), fallback ke encStr.

### Keamanan
- `/api/status` gak bocorin key (verified: `"sk-" not in output`, `"Bearer" not in output`).
- Master key file `~/.routerku-master.key` chmod 600.
- Kalau master key hilang/berubah → key gak bisa di-decrypt → provider gak jalan. **Backup master key!**

### Verifikasi (2026-08-30)
- `node --check router.mjs` → OK
- pm2 restart routerku → loaded 13 providers, 5 combos
- `/health` → ok: true, 13 providers
- `/api/status` → no key leak
- Chat test `model=Free-All` → 200, model `glm-5p2`, response OK (bukti decrypt → upstream accept)

## Fitur v6: response cache (2026-09-04)

**Status: AKTIF ✅** — request identik non-stream dijawab dari cache, tanpa hit upstream (hemat quota).

- Key = sha256(model + messages + temperature/top_p/max_tokens/stop/jumlah tools), 32 hex char.
- In-memory Map (LRU, default max 500) + persist `~/.routerku-resp-cache.json` (debounce 5s, restore saat startup kalau belum expired).
- TTL default 3600s. Env: `ROUTERKU_RESP_CACHE=0` (mati), `ROUTERKU_RESP_TTL` (detik), `ROUTERKU_RESP_MAX` (entri).
- Cuma non-stream. Bypass per-request: `{"cache": false}` atau `{"nocache": true}` di body, atau pakai `stream:true`.
- Header response: `X-Routerku-Cache: HIT/MISS/OFF`.
- Endpoint: `GET /api/cache/stats` (publik: enabled/hits/misses/size/max/ttlSec), `POST /api/cache/clear` (auth).
- Restart routerku = kill pid + `cd ~/routerku && nohup node router.mjs > ~/.routerku-out.log 2>&1 &` (jalan plain node, BUKAN pm2 — cek via `pgrep -af router.mjs`).
- Verifikasi: 2x request identik → req1 `MISS`, req2 `HIT`, stats `hits:1 misses:1 size:1`.

## Fitur v2 selanjutnya (belum ada)

RPM/RPD rate tracking, smart retry + circuit breaker, API key rotation (multi-key per provider), multi-protocol (Anthropic/Gemini/Ollama). Konsep acuan: FreeLLMAPI (MIT) — tapi codebase-nya 98k LOC, routerku sengaja minimal.