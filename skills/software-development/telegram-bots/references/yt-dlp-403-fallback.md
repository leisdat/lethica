# yt-dlp 403 Forbidden — YouTube SABR fallback (Termux 2026-08-23 verified)

YouTube `SABR-only` experiment broke default web client.

## Symptom
```
yt-dlp gagal: ERROR: unable to download video data: HTTP Error 403: Forbidden
```
Seen on `phone-storage-bot-pro` after user pasted YT link; `yt-dlp 2026.06.09 --js-runtimes node` failed, while same URL worked earlier.

## Fix verified on Termux
```bash
pip install -U yt-dlp   # 2026.06.09 → 2026.08.19
yt-dlp --version        # 2026.08.19
# direct probe: android client works
yt-dlp --extractor-args "youtube:player_client=android" --no-playlist \
  -f "bv*[height<=360][ext=mp4]+ba[ext=m4a]/b" --merge-output-format mp4 \
  -o "downloads/%(title).20s.%(ext)s" "https://www.youtube.com/watch?v=jNQXAC9IVRw"
# exit:0 → Me at the zoo.mp4 614KB
```

## Bot implementation (`bot.py:download_via_ytdlp`)
- `pip` update is safe in Termux (no maturin needed, unlike google-genai).
- Keep 3 attempts, only retry on 403/SABR/Forbidden — other errors fail fast:
```python
attempts = [
  (["yt-dlp","--js-runtimes","node","--no-playlist","-f",fmt,"--merge-output-format","mp4","-o",tpl,url], "web"),
  (["yt-dlp","--extractor-args","youtube:player_client=android","--no-playlist","-f","bv*[height<=720][ext=mp4]+ba/b","-o",tpl,url], "android"),
  (["yt-dlp","--extractor-args","youtube:player_client=ios","--no-playlist","-f","bv*[height<=720][ext=mp4]+ba/b","-o",tpl,url], "ios"),
]
for cmd,label in attempts:
  proc = await asyncio.create_subprocess_exec(*cmd, stdout=PIPE, stderr=PIPE)
  stdout,stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
  if proc.returncode==0: log.info(f"yt-dlp ok via {label}"); break
  if "403" not in err and "Forbidden" not in err and "SABR" not in err: raise RuntimeError(err)
else: raise RuntimeError(f"403 all clients: {last_err}")
```
- Pre-clean `DOWNLOAD_DIR.glob("*")` where `mtime>300s` before each download (previous `ls downloads` showed 33 MB stale pile).
- Downstream `on_link` must `require_auth` first (added after login feature), otherwise unauthed users get silent drop.

## User-facing message
On final failure: `yt-dlp gagal (403 Forbidden semua client): … — coba link lain / video private/member-only?` so user knows to try another URL instead of retrying forever.
