# Phone Vault Pro — Professional Polish & Optimizations (2026-08-23)

Session: letticha / Phone Vault Pro v2.1, 143 files. Consolidated learnings from cache, dedup, SABR, markdown, auth, dashboard.

## 1. Cache + Dedup (storage.py)
- `data.json` 50K+ with 100+ files → disk read on every /list is slow.
- Pattern: RAM cache keyed by mtime:
```python
_CACHE=None; _MTIME=0
def load_db():
    if DATA_FILE.exists():
        m=DATA_FILE.stat().st_mtime
        if _CACHE and m==_MTIME: return _CACHE
        db=json.loads(DATA_FILE.read_text()); _CACHE=db; _MTIME=m; return db
def save_db(db): DATA_FILE.write_text(...); _CACHE=db; _MTIME=DATA_FILE.stat().st_mtime
```
- Dedup: check `file_unique_id` before add_file:
```python
def is_duplicate(uid, fid): return any(f.get("file_unique_id")==fid for f in get_user_files(uid))
# in on_file:
if entry.get("file_unique_id") and is_duplicate(uid, entry["file_unique_id"]):
    await msg.reply_text("⚠️ File sudah ada (duplicate) — skip")
    return
```

## 2. Markdown escaping (list crash)
- Symptom: `BadRequest: Can't parse entities at byte offset 1016` on /list with names like `Y2meta__ lirik (320 kbps).mp3`
- Cause: `_ * ` ` [ ]` in filenames + ParseMode.MARKDOWN
- Fix:
```python
def esc(s): return s.replace("`","'").replace("*","").replace("_"," ").replace("[","(").replace("]",")")[:42]
lines=[f"`{id}`  #{folder}  {esc(name)}" for ...]
header="━━━━━━━━━━━━━━━━━━━━\n📦 *PHONE VAULT* — {len} file • Hal {page}/{total}\n━━━━━━━━━━━━━━━━━━━━"
```
- Also use header borders for professional look (Help/List/Folders/Stats all use ━━━).

## 3. yt-dlp SABR 403 (YouTube 2026)
- Error: `8iuLXODzL04: Only images are available / Requested format is not available / 403 Forbidden` + SABR warning.
- Root: YouTube SABR experiment, need `formats=missing_pot`.
- Fix: yt-dlp>=2026.08.19 + add missing_pot to every client:
```python
attempts=[
  (["yt-dlp","--js-runtimes","node","--extractor-args","youtube:formats=missing_pot", ...], "web"),
  (["yt-dlp","--extractor-args","youtube:player_client=android;formats=missing_pot", ...], "android"),
  (["yt-dlp","--extractor-args","youtube:player_client=ios;formats=missing_pot", ...], "ios"),
]
# on 403/Forbidden/SABR → try next; else fail fast
```
- Verified: `8iuLXODzL04` YOASOBI 7.99MiB downloads 100% only with missing_pot.

## 4. Auth: Telegram login + /akses sharing
- Both dashboard (cookie pv_pin) and Telegram use PIN 292929, AUTH_TTL 86400, auth.json.
```python
def is_authed(uid): return auth.json.get(str(uid)) and time.time()-ts < TTL
async def require_auth(update):
    if not is_authed(uid): await reply("🔒 Login dulu: /login 292929"); return False
# direct PIN as message: if text.strip()==TELEGRAM_PIN → set_authed
```
- Sharing: `db["access"]={owner:[allowed_ids]}`, helpers `is_allowed`, `find_file_any`, `get_accessible_files`, `add_access/remove_access/list_access`
- Commands: /akses add/list/del, /myid, /shared. `get` handler must try own then `find_file_any+is_allowed`.

## 5. Dashboard filter + thumbnail
- Dashboard has folder/type dropdowns, search, counter `X / 143 file`, cache RAM note.
- Thumb endpoint must serve document JPGs, not only photo type:
```python
name=target["name"].lower()
is_img = target["type"]=="photo" or name.endswith((".jpg",".jpeg",".png",".webp",".gif"))
```
- Frontend: `isImg` by extension, `<img src="/thumb/{id}" loading=lazy>`; counter updates on filter.

## 6. Professional text polish (Help/List/Folders/Stats)
- Help v2.1: bordered sections SIMPAN FILE / PERINTAH UTAMA / AKSES & KEAMANAN / LAINNYA / DASHBOARD WEB, code fences for commands.
- List: `id  #folder  type  esc(name)  size` with ━━━ header
- Folders: `FOLDERS — {total} file • {n} folder` + `#{k:<12} {v:>3} file` + tap hint
- Stats: bordered + `Total: X file • Y` + User id + Tipe + Folder tables + dashboard PIN footer
- Saved: `✅ Tersimpan` bordered + `esc(name)` + `ID:xxx • #folder • size • date`

See bot.py in phone-storage-bot-pro for full implementations.
