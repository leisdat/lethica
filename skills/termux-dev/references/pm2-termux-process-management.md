# PM2 & long-running Node processes on Termux

For user-run daemons on Termux (routerku, media-dl, bots), prefer PM2 over Hermes
`terminal(background=true)`: PM2 survives the Hermes session ending, auto-respawns on
crash, and can be made boot-persistent via Termux:Boot.

## Start a service under PM2
```bash
pm2 start path/to/router.mjs --name routerku   # fork_mode, 1 instance
pm2 save                                        # persist to ~/.pm2/dump.pm2 (REQUIRED before boot script works)
pm2 list                                        # status / pid / uptime / restart-count
pm2 restart <name>; pm2 logs <name>
```

## Boot persistence — use Termux:Boot, NOT `pm2 startup`
- `pm2 startup` FAILS on Termux (no systemd/init system; it throws a Node TypeError).
  Do not run it.
- Correct approach: add a script under `~/.termux/boot/` (must be executable):
  ```bash
  #!/data/data/com.termux/files/usr/bin/bash
  export PATH=/data/data/com.termux/files/usr/bin:$PATH
  pm2 resurrect
  ```
  `pm2 resurrect` restores everything saved by `pm2 save`.
- Caveat: Termux:Boot only fires if the "Termux:Boot" Android app is installed; otherwise
  the script is inert (service still runs while PM2 isn't killed by Android's RAM manager).
- `pm2 list` only shows currently-loaded apps. When checking what's actually running, also
  grep the process table (`ps aux | grep <script>`) — a leftover orphan from a prior
  non-PM2 start may still own the port even though it's absent from `pm2 list`.

## Crash-loop diagnosis (EADDRINUSE from an orphan)
Symptom in `pm2 list`: `↺` (restart count) climbing fast, uptime stuck at `0s`, status
"online" but it keeps restarting. Root cause here: an earlier non-PM2 `node server.mjs`
started via background=true was "killed" via Hermes process tool but the child actually
ORPHANED and kept holding the port → PM2 instance can't bind → EADDRINUSE → crash loop.

Fix sequence (verified live):
1. `ps aux | grep '<script>'` to find BOTH the PM2-managed proc AND the orphan pid.
2. `kill -9 <orphan-pid>` (kill -9, not plain kill — the process tool's kill didn't reap it).
3. `pm2 restart <name>`, then confirm: `↺` stops climbing, uptime accumulates, pid stable,
   exactly ONE process in `ps`.
4. `curl http://127.0.0.1:<port>/api/status` must return a live payload.
Also `pm2 delete <name>` before `pm2 start` clears a stale/resurrected entry.

## Port checks lie on Termux
- `netstat -tlnp | grep <port>` and `lsof`/`ss` often report "not listening" even when the
  service responds — Termux socket formatting/availability quirks. Do NOT trust a netstat
  miss as "service is down". The authoritative check is `curl http://127.0.0.1:<port>/...`
  and reading the app's own log line ("listening on http://0.0.0.0:<port>").

## WhatsApp: wrangler/workerd can't run on android-arm64
- `npm install wrangler` on Termux fails at the `workerd` postinstall with
  `Error: Unsupported platform: android arm64 LE` — workerd ships no android-arm64 binary,
  so `wrangler dev`/`deploy` and local Workers runtime are unavailable on-device.
- This is a permanent platform constraint, not a fixable setup issue. For deploying a
  Cloudflare Worker from Termux, plan the manual REST API route (curl + multipart form
  with `Content-Type: application/javascript+module`) instead — see the Cloudflare
  "manual-deploy" docs pattern. (Not yet exercised on this device; validate before relying on it.)