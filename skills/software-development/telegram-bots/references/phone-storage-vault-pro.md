# Phone Storage Vault Pro v2 — Modular professional layout (2026-08, proven)

Evolved from v1 (`~/phone-storage-bot/bot.py`) to `~/phone-storage-bot-pro/` after user requested "rapihin file" + "bot dll nya agar profesional".

## Layout
```
phone-storage-bot-pro/
├── bot.py              # entry: polling + web, imports config/storage/ui/dashboard
├── config.py           # TOKEN, BACKUP_CHANNEL, WEB_HOST/PORT, BRAND_NAME/VERSION, DATA_FILE/DOWNLOAD_DIR/LOG_FILE
├── storage.py          # load_db/save_db with daily .bak.YYYYMMDD via shutil.copy + add/delete/find
├── handlers/ui.py      # MENU_KB (4 rows), HELP_TEXT branded, parse_folder + auto_folder_for + human_size/fmt_date/gen_id
├── web/dashboard.py    # create_app() — Inter font, dark-mode, header PV, /api/files + /download/{fid} proxy via getFile
├── data.json + data.bak.YYYYMMDD
├── downloads/          # yt-dlp temp, auto-unlink
├── logs/bot.log        # FileHandler + StreamHandler wired in bot.py
└── .env.example / requirements.txt / README.md
```

## Auto-folder by extension (key learning)
Manual `#tag` wins; if `parse_folder()` returns `umum`, fall through:

```python
def auto_folder_for(name: str, typ: str) -> str:
    n=name.lower()
    if n.endswith(".pdf"): return "pdf"
    if n.endswith((".doc",".docx",".xls",".xlsx",".ppt",".pptx",".txt",".rtf")): return "dokumen"
    if n.endswith((".mp3",".m4a",".wav",".flac",".ogg",".aac",".wma")): return "musik"
    if n.endswith((".mp4",".mkv",".mov",".avi",".webm",".flv")): return "video"
    if n.endswith((".jpg",".jpeg",".png",".webp",".heic",".bmp",".gif")): return "foto"
    if n.endswith((".zip",".rar",".7z",".tar",".gz")): return "arsip"
    if typ=="voice": return "voice"
    if typ=="sticker": return "sticker"
    if typ=="photo": return "foto"
    if typ=="audio": return "musik"
    if typ=="video": return "video"
    return "umum"

# in on_file:
if entry.get("folder")=="umum":
    auto=auto_folder_for(entry.get("name",""), entry.get("type",""))
    if auto!="umum": entry["folder"]=auto
```

## Organize command
`/organize` + keyboard `🗂️ Rapihin` loops `umum` rows through `auto_folder_for` and saves. `/move <id> <folder>` still works.

## Logging
```python
logging.basicConfig(level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()])
log.info(f"Starting {BRAND_NAME} {VERSION} — data={DATA_FILE}")
# + per-save: log.info(f"save {fid} #{folder} by {uid}")
```

## Dashboard Pro (port 8081)
Started in `post_init` alongside `set_my_commands`. `create_app()` returns aiohttp app with Inter, dark-mode, header `PV | Phone Vault Pro • v2.0`, search input, cards. `GET /download/{fid}` resolves file_id → `api.telegram.org/bot{TOKEN}/getFile` → proxy bytes with `Content-Disposition: attachment`.

## Link downloader
`on_link` detects platform via `PLATFORM_RE` dict, then:

```python
cmd=["yt-dlp","--js-runtimes","node","--no-playlist","--no-warnings","-f",fmt,"--merge-output-format","mp4","-o", str(DOWNLOAD_DIR/"%(title).50s_%(id)s.%(ext)s"), url]
proc=await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
# pick newest file in DOWNLOAD_DIR with mtime <120s, re-upload as video/document, add entry with source_url, unlink temp
```

`fmt` map: youtube→720p, tiktok/instagram→480p.

## Menu Pro (must match regex)
`[[List, Search],[Folders, Rapihin],[Stats, Dashboard],[Help, Clear]]` → `filters.Regex(r"^(📋 List|🔍 Search|📂 Folders|🗂️ Rapihin|📊 Stats|🌐 Dashboard|❓ Help|🗑️ Clear)$")`

## Migration + single-instance
Copied `~/phone-storage-bot/data.json` → `~/phone-storage-bot-pro/data.json`; `save_db` creates `.bak.YYYYMMDD` once/day. Kill old with `ps aux | grep "python3 bot.py" | awk '{print $2}' | xargs -r kill` (pgrep matches wrapper → verify with `ps`). Run `BOT_TOKEN=... python3 bot.py` as `terminal(background=true)` and verify `curl /api/files`.

## Verified run (Termux, 2026-08-23)
```
syntax OK / imports OK
Dashboard Pro jalan di http://0.0.0.0:8081
HTTP 200 /api/files → foto/musik auto-split, e.g. IMG_20240410_073330.jpg #foto 3.3MB
logs/bot.log tails save + HTTP 200
data.json 52KB (1545 lines) + data.bak.20260823
```
