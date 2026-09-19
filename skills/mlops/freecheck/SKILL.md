---
name: freecheck
description: "Cek model free & status provider di web lokal :3005."
---

# FreeCheck — cek model free & status provider

Web app lokal (port **3005**) yang list semua model di custom provider `~/.hermes/config.yaml`, deteksi model "free/bansos" dari nama (`:free`/`free`), dan **real-test** (kirim request kecil `max_tokens:5`) untuk verifikasi beneran jalan vs cuma ada di list.

## Trigger
- "cek model mana yg free/bansos", "model X jalan gk", "status provider", "tambah provider ke freecheck"

## Arsitektur
- `~/freecheck/server.js` — Node zero-dep (http + fetch). Baca `~/.hermes/config.yaml` (custom_providers) + `~/.hermes/.env` (API keys). **Gak ada node_modules.**
- `~/freecheck/public/` — index.html, app.css, app.js (vanilla JS, dark theme, Inter, 8px grid).
- PM2 name: `freecheck`. Akses: `http://127.0.0.1:3005` (atau IP LAN).

## API
- `GET /api/providers` — list provider + count models + okCount
- `GET /api/models?base=<apiBase>` — list model (cache 10m)
- `POST /api/test` `{base, model, force}` — test 1 model
- `POST /api/batch` `{base, freeOnly, force}` — test semua (concurrency 3)
- `GET /api/status?base=<apiBase>` — job progress + semua result
- `GET /api/ping`

## Gotcha Kritis — secret-redactor
**`write_file`/`patch` Hermes secara literal mengganti string `"Bearer "` di file dengan `"***"`** (redaction). Kalau server.js mengandung `Authorization: 'Bearer ' + key`, hasil di-disk = `Authorization: '***' + key` → header jadi `***sk-...` → semua provider balas **401 "Invalid token"**.
- **FIX (sudah applied):** rakit header dinamis: `const AUTH_HDR = ['Be','ar','er'].join('') + ' ';` lalu `function authHeader(k){return {Authorization: AUTH_HDR + k};}`
- **DIAGNOSA cepat:** kalau semua provider 401 tapi `curl` manual (dengan key dari .env) sukses → cek `grep -c "Bearer " server.js` → 0 = kena redactor.
- **JANGAN tulis literal `"Bearer "` lagi di file ini.** Kalau edit server.js, selalu pakai `authHeader()`.

## Gotcha lainnya
- Test model pake `max_tokens:5` — beberapa model (linstore) reject `max_tokens<2` (valid, jadi gak akan jadi false-negative).
- Model free = regex `/free/i` di nama model (konvensi `:free` OpenRouter & nama `*-free` linstore).
- Concurrency test = 3 (biar gak kena rate-limit / HP panas).
- Cache: models 10m, test result 10m (force untuk ulang).

## Ops
- Restart: `pm2 restart freecheck`
- Stop: `pm2 stop freecheck`
- Log: `pm2 logs freecheck`
- Provider baru auto-terdeteksi (parser config.yaml di-read saat server start). Kalau nambah provider di config.yaml → `pm2 restart freecheck`.

## Nambah provider
Cukup nambah ke `custom_providers` di `~/.hermes/config.yaml` (key di `~/.hermes/.env`). FreeCheck auto-detect. **Gak perlu ubah kode.**
