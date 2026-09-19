# Phone Storage Vault — Telegram file_id as storage (2026-08, proven on Termux)

Pattern from `~/phone-storage-bot/bot.py` — bot that turns Telegram into unlimited phone storage. Only `data.json` metadata is kept locally; actual bytes stay on Telegram.

## Core idea
- Store `file_id` + `folder` + `caption` + `size` + `date` in `~/phone-storage-bot/data.json` per user (`users->{uid}->[entries]`).
- Bot API limit 50 MB/file respected. Text notes also stored (`type=text`).
- `folder` auto-parsed from caption/text; default `umum`. Migration: old rows lacking `folder` get `umum` on load.

## Folder parsing
```python
def parse_folder(caption: str) -> str:
    m = re.search(r"#(\w+)", caption)
    if m: return m.group(1).lower()[:20]
    m = re.search(r"^\[(\w+)\]", caption.strip())
    if m: return m.group(1).lower()[:20]
    m = re.search(r"^(\w+):", caption.strip())
    if m and len(m.group(1))<=15 and m.group(1).lower() not in ["http","https"]:
        return m.group(1).lower()
    return "umum"
```
Usage: `#kuliah`, `[kerja] laporan`, `kuliah: catatan`. Clean caption with `re.sub(r"#\w+","",caption)`.

## Commands
- `/list [folder]` — filter by folder, paginated (PAGE=5), callback prefixes `list:<page>` vs `folder:<name>:<page>` kept distinct
- `/folders` — `Counter(folder)` with inline buttons `folder:<name>:0`
- `/move <id> <folder>` — update `folder` field in DB
- `/search <q>` searches `name/caption/text/folder`
- `/stats` shows per-type and per-folder counters + `BACKUP_CHANNEL` status
- `/clear` confirm via inline

## Persistent reply keyboard
```python
MENU_KB = ReplyKeyboardMarkup(
    [[KeyboardButton("📋 List"), KeyboardButton("🔍 Search")],
     [KeyboardButton("📂 Folders"), KeyboardButton("📊 Stats")],
     [KeyboardButton("❓ Help"), KeyboardButton("🗑️ Clear")]],
    resize_keyboard=True, is_persistent=True)
# in post_init: await app.bot.set_my_commands([...])
# register BEFORE generic file handlers:
app.add_handler(MessageHandler(filters.Regex(r"^(📋 List|🔍 Search|📂 Folders|📊 Stats|❓ Help|🗑️ Clear)$"), on_menu_text))
```

## Backup channel
- Env `BACKUP_CHANNEL` (`-100...` or `@username`). On save:
```python
if BACKUP_CHANNEL:
    try: await ctx.bot.forward_message(chat_id=BACKUP_CHANNEL, from_chat_id=msg.chat_id, message_id=msg.message_id)
    except Exception as e: print(f"backup gagal: {e}")
```
- User creates private channel, adds bot as admin, forwards one msg to @userinfobot for ID.

## Pitfalls hit
- Restart `Conflict: terminated by other getUpdates` — kill with `ps aux | grep bot.py | awk '{print $2}' | xargs kill -9` (pgrep matches wrapper). Wait 2-3s.
- ID collision: `gen_id()` uses `int(time.time()*1000)%100000000` — short but unique enough for personal use.

See full bot: `~/phone-storage-bot/bot.py` (17276 bytes, 2026-08).
