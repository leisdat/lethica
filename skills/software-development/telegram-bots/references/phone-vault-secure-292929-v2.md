# Phone Vault Pro Secure — patterns distilled 2026-08-23

Source session: letticha / Phone Vault Pro v2.1 (143 files, Termux, PIN 292929)

## Auth (Telegram + Dashboard same PIN)
- `.env` manual load in config.py, no python-dotenv; `BOT_TOKEN` required, `DASHBOARD_PIN=292929`, `TELEGRAM_PIN=DASHBOARD_PIN`, `AUTH_TTL=86400`
- `.env` chmod 600, `.gitignore` entry, `data.json` chmod 600
- `auth.json` = {user_id: timestamp}; `is_authed(uid)` checks TTL, `set_authed`
- `require_auth(update)` gate every handler; accept `/login <PIN>` and raw PIN text; callback `auth:login`
- Dashboard aiohttp: cookie `pv_pin` + `?pin=` fallback; `GET /` 302 → `/login`, `/api/files` 401

## Markdown escaping
- Symptom: `BadRequest: Can't parse entities at byte offset 1016` on /list with 143 files, names with __ * ` [ ]
- Fix: `esc(s)=s.replace("`","'").replace("*","").replace("_"," ").replace("[","(").replace("]",")")[:42]`; use in list/search/stats replies

## Storage cache & dedup
- storage.py: global `_CACHE` + `_MTIME`; load_db checks mtime, save_db updates cache + .bak.YYYYMMDD
- `is_duplicate(uid, file_unique_id)` before add_file → skip with duplicate reply

## Sharing /akses
- data.json["access"] = {owner_id: [allowed_ids]}
- helpers: add_access, remove_access, list_access, is_allowed, get_accessible_files, find_file_any
- Commands: /akses add <numId>, /akses list, /akses del, /myid, /shared; get checks is_allowed

## yt-dlp 403 fallback
- Update yt-dlp 2026.06.09 → 2026.08.19 (`pip install -U yt-dlp`)
- Try 3 clients: web+node → android → ios; retry only on 403/Forbidden/SABR strings; log `yt-dlp ok via <client>`

## Polished UI
- Help v2.1 with border ━━━, sections, monospace commands; list header `PHONE VAULT — N file • #folder Hal x/y`; folders table aligned; stats table; saved reply with border + esc(name) + date
