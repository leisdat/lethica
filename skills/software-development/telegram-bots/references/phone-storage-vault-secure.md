# Phone Vault Pro Secure v2.1 — PIN hardening (2026-08, verified)

Extends `phone-storage-vault-pro.md`. Applied after user asked "keamanan gimana" and chose PIN 292929.

## Threat addressed
- `config.py` fallback `TOKEN or "8812..."` leaked token if `.env` missing; dashboard `8081` open to any WiFi peer (`/api/files` without auth); no rate limit.

## Config secure (`config.py`) — no hardcode
Loads `.env` manually (no python-dotenv on Termux), then mandatory `_need("BOT_TOKEN")`:
```python
_env = BASE_DIR / ".env"
if _env.exists():
    for line in _env.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith("#") or "=" not in line: continue
        k,v=line.split("=",1); os.environ.setdefault(k.strip(), v.strip())
def _need(key):
    v=os.environ.get(key)
    if not v: raise RuntimeError(f"Config {key} wajib di .env")
    return v
TOKEN=_need("BOT_TOKEN")
DASHBOARD_PIN=os.environ.get("DASHBOARD_PIN") or "123456"
TELEGRAM_PIN=os.environ.get("TELEGRAM_PIN") or DASHBOARD_PIN
AUTH_TTL=int(os.environ.get("AUTH_TTL") or "86400")
```
`.env` (chmod 600):
```
BOT_TOKEN=8812706397:AAH...
DASHBOARD_PIN=292929
WEB_PORT=8081
```
`.gitignore` must list `.env`, `__pycache__/`, `logs/`, `downloads/`, `data.bak.*`. After import, `chmod 600` on `.env` + `data.json`.

## Dashboard PIN (`web/dashboard.py`)
Gating helper:
```python
def _authed(req): return req.cookies.get("pv_pin")==DASHBOARD_PIN or req.query.get("pin")==DASHBOARD_PIN
```
Routes: `GET /login` (form), `POST /login` (check pin → set_cookie pv_pin 7d + 302 /), `GET /logout` (del_cookie + 302 /login), `GET /` and `GET /api/files` and `GET /download/{fid}` all check `_authed` → 401/302 if false. Verified: `curl /` → 302, `curl /api/files` → {"error":"unauthorized"}, `curl /api/files?pin=292929` → 200.

## Telegram PIN (`bot.py`)
`auth.json` = `{uid: timestamp}`. Helpers `_load_auth/_save_auth/is_authed/set_authed(+AUTH_TTL)`.
```python
async def require_auth(update):
    if is_authed(update.effective_user.id): return True
    await (update.message or update.callback_query.message).reply_text(
        "🔒 Login dulu — `/login 292929` atau kirim `292929`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔓 Login", callback_data="auth:login")]]))
    return False
```
Wrap every user-facing handler: `start`, `list_cmd`, `folders_cmd`, `move_cmd`, `organize_cmd`, `search_cmd`, `get_cmd`, `delete_cmd`, `stats_cmd`, `clear_cmd`, `on_menu_text`, `on_callback` (except `auth:login`). `on_file` first checks direct PIN text: `if text.strip()==TELEGRAM_PIN → set_authed + reply ✅`. Add `/login <PIN>` and `/logout` commands and register them + expose in `setMyCommands`.

## Rate limit + log sanitization (`bot.py`)
```python
_RATE={}
def _hit(uid):
    now=time.time(); b=_RATE.setdefault(str(uid),[])
    b[:]=[t for t in b if now-t<10]
    if len(b)>=10: return False
    b.append(now); return True
class SanitizeFilter(logging.Filter):
    def filter(self, r):
        if "file_id" in r.getMessage(): r.msg=re.sub(r"file_id.{0,30}","file_id=***", r.msg)
        return True
for h in logging.getLogger().handlers: h.addFilter(SanitizeFilter())
```
Call `_hit` at top of `on_file` (after PIN-direct check). Log only `save {fid} {name[:40]} #{folder} by {uid} size=...`.

## Verification (Termux 2026-08-23)
```
TOKEN via .env OK pin 292929 2.0.1-secure / compile OK
Bot Pro polling... Dashboard Pro jalan di http://0.0.0.0:8081
curl / → 302 Found
curl /api/files → {"error":"unauthorized"}
curl /api/files?pin=292929 → [{"id":"94635960","name":"DSC_0010.JPG","folder":"foto"...}]
ls -l .env data.json → -rw------- (600)
auth.json absent until first login; /login 292929 → ✅ Login berhasil 24h
```
