# Termux Android 13 — Networking & Service Health (2026-09-01)

## Netlink blocked → traditional net tools fail
On Redmi Note 11 / Android 13 (Termux):
- `ip route get …`, `ifconfig`, `netstat -tlnp`, `ss -tlnp`, `cat /proc/net/route`, `cat /proc/net/tcp`, `dumpsys wifi` → all `Permission denied` / `Cannot open netlink socket` / `Permission Denial: can't dump WifiService`.
- `hostname -I` → `invalid option -- 'I'` (toybox hostname berbeda).

**Workaround IP LAN (verified 2026-09-01, 10.65.119.55):**
```python
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
print(s.getsockname()[0])  # → LAN IP
s.close()
```
No extra permission, no netlink. Use for building `http://<IP_LAN>:<port>/dashboard` links (9Router :20128, Routerku :20130).

## Service health — curl, not ss/netstat
- `ss`/`netstat`/`lsof` lie on Termux (empty even when listening). **Verify with curl:**
  - `curl -s -m 3 http://127.0.0.1:20128/` → 307 redirect to `/dashboard` (9Router healthy)
  - `curl -s -m 3 http://127.0.0.1:20128/health` / `/api/health` → JSON
  - `curl -s -m 3 http://127.0.0.1:20130/health` → `{"ok":true,"providers":16,"combos":[...]}` (Routerku healthy)
- `curl -I http://127.0.0.1:20128/` → `307 Temporary Redirect` + `location: /dashboard` also signals healthy.

## 9Router start quirk re-verified (2026-09-01)
- `9router -n --skip-update` prints banner `🚀 9router v0.5.x` + `Server: http://localhost:20128` but **port never opens** (`curl` → 000) until next start with `--log`.
- Fix: `9router -n --skip-update --log` background=true, wait 6–7s, curl check. Warm-up ~10s (not instant).
- Hermes `terminal` tool: don't wrap with `nohup … &` or `&` inline — use `terminal(background=true, notify=["listening","9Router"])`. Foreground wrapper is rejected.

## Routerku auto-sync (reading 9Router DB)
- `~/routerku/router.mjs` reads DB `~/.9router/db/data.sqlite` (readOnly) — tables `providerNodes`, `providerConnections`, `combos`, `apiKeys`.
- Auto-reload: `fs.watchFile(DB_PATH, {interval: 2000})` → reload in ~2s, log `[routerku] auto-reload DB` to `~/routerku/routerku.log`.
- Manual: `curl -X POST http://127.0.0.1:20130/api/reload` (bearer auth).
- This session host runs bare `node router.mjs` (no PM2, `pm2 list` empty) per memory `TIDAK PM2-managed — kill PID + node ~/routerku/router.mjs bg`. Watchdog `~/routerku/watchdog.sh` checks `curl /health` every minute and auto-restarts via `pkill -f 'node router.mjs'; nohup node router.mjs`.
