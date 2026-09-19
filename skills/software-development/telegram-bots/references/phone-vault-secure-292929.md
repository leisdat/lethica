# Phone Vault Pro Secure — reference for telegram-bots hardening

Pattern proven 2026-08-23, Termux Android, python-telegram-bot v22 + aiohttp.

## Config (.env)
```
BOT_TOKEN=xxx
DASHBOARD_PIN=292929
TELEGRAM_PIN=292929
AUTH_TTL=86400
WEB_PORT=8081
```
config.py manually parses .env, chmod 600, raises if BOT_TOKEN missing.

## Auth files
- auth.json { "8598374363": 178749... } TTL check in is_authed()
- Cookie pv_pin for web, ?pin= fallback

## Guards
Wrap every handler entry: if not await require_auth(update): return
require_auth sends "🔒 Login dulu /login 292929" with button.

## yt-dlp fallback
Attempts = [
  (web+node fmt 720p),
  (android client bv*[height<=720]),
  (ios client)
]
Retry only on 403/Forbidden/SABR, else raise immediately. Log each attempt.
Update via pip install -U yt-dlp (2026.08.19 fixes SABR).

## Rate limit
_RATE dict user->list[timestamps], 10 per 10s window.
