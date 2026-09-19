# PM2 Node Backend Audit Chain (NOVA case 2026-09-02)

Captured diagnostic chain from auditing NOVA (Extension Hub Pro) on Termux.
12 bugs surfaced one at a time, each only visible after the previous was fixed.
Order matters; don't skip steps.

## The chain

| # | Symptom | Root cause | Fix |
|---|---------|------------|-----|
| 1 | `[DEP0169] url.parse() deprecation` (cached log noise) | `app/server.js` pakai `url.parse()` | `const { URL } = require("url")` + `new URL(req.url, ...)` |
| 2 | `<main id="content">` kosong | frontend panggil `/api/home`, endpoint tidak ada | tambah handler di `app/server.js` |
| 3 | `sources.sections is not a function` | method `sections`/`genres` tidak di-export | pakai `sources.home()` yang sudah ada |
| 4 | `runIsolated is not defined` | import tanpa destructuring | `const { runIsolated } = isolated;` |
| 5 | `Cannot find module 'latest/index.js'` | `runIsolated(e, "home")` → worker load `<ext>/home/index.js` | ganti ke `runIsolated(e, "latest", [24])` (method yang ada) |
| 6 | `WORKER_COOLDOWN` | worker crash dari bug #5 → 30s cooldown | efek dari #5, fixed dengan pakai method yang ada |
| 7 | log masih tampil warning lama | `pm2 restart` tidak flush log | `pm2 flush <service>` sebelum restart |

## Workflow (proven)

```bash
# 1. Cek status
pm2 list | grep <service>

# 2. Flush log cache (suppress noise lama)
pm2 flush <service>

# 3. Restart
pm2 restart <service>

# 4. Test endpoint langsung
curl -s http://127.0.0.1:<port>/api/<endpoint> | head -20

# 5. Cek error log baru
tail -10 ~/.pm2/logs/<service>-error.log

# 6. Kalau error, baca chain: warning → 404 → method missing → import → module path
```

## Pattern: audit order traps

1. **Cached log noise menutupi real bug.** `pm2 restart` tidak clear log. Flush dulu, baru debug. Warning `url.parse()` deprecation yang cached bisa menutupi error `Method is not a function` yang sebenarnya.

2. **Frontend ↔ Backend contract drift.** Jika `<main id="content">` kosong di browser, grep JS untuk `api('/...')` calls. Setiap endpoint yang frontend panggil HARUS ada di server handler. Jika tidak → 404 → return `{"ok":false,"error":"..."}` (silent di UI).

3. **Worker isolation module path gotcha.** `runIsolated(e, "<method>", args)` → worker nge-load `<ext>/<method>/index.js`. Untuk extension yang entry-nya `index.js` di root, method HARUS di root, bukan di subfolder. Kalau panggil method yang tidak ada → `EXTENSION_LOAD_FAILED: Cannot find module '<method>/index.js'`.

4. **Import vs destructuring.** `const isolated = require("./isolatedRuntime")` tidak expose `runIsolated` sebagai local name. Harus `const { runIsolated } = isolated;`. Error message: `runIsolated is not defined` (bukan "is not a function" — itu beda).

5. **PM2 log flush vs restart.** `pm2 restart` append. `pm2 flush` clear. Selalu flush setelah fix warning deprecation untuk bersih log sebelum iterasi berikutnya.

## Cross-project applicability

Same chain applies to any PM2-managed Node backend on Termux:
- SPECTER-style (Python/chrome) backend: warning noise → endpoint 404 → method missing → import → module path
- NOVA-style (Node/PM2/worker_threads) backend: sama
- 9Router / Routerku (Node single-process): warning noise → endpoint 404 → method missing → import → module path

The shape is the same; only the tooling differs (`pm2 logs` vs `tail` vs `journalctl`).

## Don't-skip discipline

When auditing, the temptation is to fix multiple bugs at once. **Don't.**
Each fix changes the symptom set, and a new error may only appear after the
previous one is gone. Sequential fix → verify → next.

## Reference

- `cf-agent` skill (SPECTER, same audit shape)
- `pm2-termux-process-management.md` (PM2 quirks on Termux)
- `scraper-audit-repair.md` (probe-per-capability script)
