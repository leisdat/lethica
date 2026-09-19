# Exposing a local Termux server to other networks (TV on other WiFi, 4G)

Use when the user wants a local server (e.g. NOVA :3001) reachable from a device that
is NOT on the same LAN (TV on another WiFi, phone on cellular), or wants a public/stable URL.

## 1. Find your own LAN IP — netlink is blocked
`ip addr` / `ip route` → `Cannot bind netlink socket: Permission denied`.
`termux-wifi-connectioninfo` needs the Termux:API companion app (unavailable on Play).
`ss -tlnp` shows nothing useful. WORKING TRICK — UDP connect to any reachable IP, then
read the socket's local address:

```js
// node -e
const dgram = require('dgram');
const s = dgram.createSocket('udp4');
s.on('error', () => process.exit(1));
s.connect(53, '8.8.8.8', () => { console.log(s.address().address); s.close(); });
```

Verified: returned `10.63.161.35`; `curl http://10.63.161.35:3001/api/health` → 200.
Note: UDP bind(0) then send does NOT work (address is 0.0.0.0) — it must be `connect()`.

## 2. Quick public URL, no account: localhost.run (SSH reverse tunnel)
```bash
ssh -o StrictHostKeyChecking=no -R 80:localhost:3001 nokey@localhost.run
```
- Prints `https://<random>.lhr.life` (TLS termination) — verified e2e (UI 200, /api/health 200, /api/home 200).
- **serveo.net: TIMED OUT** — don't waste time there.
- Free tier limits: URL **rotates on every reconnect** + speed limit (anti-phishing).
- Stable URL options: lhr.rocks subdomain (free, via admin.localhost.run + SSH key) or custom domain ($9/mo).

### Productionize it (auto-reconnect under PM2)
Wrapper loop script (e.g. `<proj>/nova-tunnel.sh`):
```bash
#!/data/data/com.termux/files/usr/bin/bash
export PATH=/data/data/com.termux/files/usr/bin:$PATH
while true; do
  echo "[tunnel] connect $(date)"
  ssh -o StrictHostKeyChecking=no -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 80:localhost:3001 nokey@localhost.run
  echo "[tunnel] disconnected $(date), retry in 5s"; sleep 5
done
```
`pm2 start nova-tunnel.sh --name nova-tunnel && pm2 save` (boot-resurrect via existing ~/.termux/boot script).
- PITFALL: don't pipe the ssh output through `grep` in the wrapper — buffering hides the URL
  for minutes. Log raw; then `grep -E "lhr.life" ~/.pm2/logs/<name>-out.log`.
- When restarting the tunnel, the old URL dies — re-grep the new one.
- Kill stray duplicate tunnels: `pgrep -af "localhost.run" | grep -v "pgrep\|bash -lic"` → kill the bare `ssh` PIDs.

## 3. Stable permanent URL: Cloudflare Tunnel (user's own domain)
- **cloudflared GitHub prebuilt binary FAILS on Termux**: `unexpected e_type: 2` (glibc).
  WORKS: **`pkg install cloudflared`** (Termux repo ships it; v2026.6.1 verified).
- Named tunnel recipe: domain → Cloudflare (add domain, switch NS from registrar, e.g. Domainesia) →
  Zero Trust → Networks → Tunnels → Create → `cloudflared tunnel login` (user pastes the URL) →
  `cloudflared tunnel run --token ...` under PM2. Free, permanent, fast (CF edge).
- Quick tunnel (no account): `cloudflared tunnel --url http://localhost:3001` → random
  trycloudflare.com URL; fine for demos, rotates on restart.

## 4. PaaS fallbacks (if user accepts signup)
- **Render free tier REQUIRES a payment card** (anti-abuse, not charged on free). Railway CLI has
  no android-arm64 build (see deploy-from-termux.md).
- Vercel is static-only (no Node) — fine for the UI half with API rewrites, useless as the backend host here.

## Decision guidance for this user
- Only home + same WiFi → no tunnel at all: `http://<IP-LAN>:3001` (detect via trick above) + PM2 nova + wakelock.
- TV on OTHER WiFi / wants shareable → cloudflared named tunnel on their domain (permanent) if
  they'll do the NS switch; otherwise localhost.run loop (URL rotates — set expectations).
