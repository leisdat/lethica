# /akses sharing — Phone Vault Pro (2026-08-23 verified)

## Goal
Let owner `A` grant `B` access to all files under `A` without merging DBs. User asked: "Tambahin fitur /akses biar bisa tambahin orang bisa akses file kita".

## Storage (`storage.py`)
New top-level key `access` in `data.json`:
```json
{"users": {"8598374363": [...]}, "access": {"8598374363": ["123456789"]}}
```
Helpers (all `str()`-coerced):
- `find_file_any(fid) -> (file, owner)` scans all users
- `is_allowed(owner, requester)` → `owner==requester` or `requester in access[owner]`
- `get_accessible_files(uid)` → own + shared (each shared file gets extra `_owner` field, sorted by date)
- `add_access(owner,target)` / `remove_access` / `list_access`

`load_db()` migrates old DBs missing `access`.

## Bot (`bot.py`)
- `auth.json` login still required (`require_auth`); sharing does NOT bypass PIN.
- Commands: `/akses [list|add <id>|del <id>]`, `/myid` (replies `ID + username + hint`), `/shared` (lists `get_accessible_files` filtered to `_owner` entries).
- `add` only accepts numeric ID (rejects `@username` with hint to use `/myid`); on success notifies target via `bot.send_message` (best-effort).
- `get_cmd` and `CallbackQueryHandler get:` now try `find_file` first, then `find_file_any + is_allowed`; else `❌ Tidak ketemu / gak ada akses`.
- `setMyCommands` extended with `akses/shared/myid`.

## Verification
```
python3 -m py_compile bot.py && python3 -m py_compile storage.py → akses syntax OK
Bot Pro polling... Dashboard Pro jalan di http://0.0.0.0:8081
/myid → 🆔 ID lu: 8598374363
/akses list → Belum ada orang … /akses add …
/akses add 123… → ✅ … sekarang bisa akses via /shared & /get
/shared (as recipient) → 🔗 File shared ke lu … (with _owner)
```

## Pitfall to keep
Username→ID resolution not attempted (Telegram username ≠ stable ID and not in DB unless user chatted). Always require numeric ID from `/myid`.
