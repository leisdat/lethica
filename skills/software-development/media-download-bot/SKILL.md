---
name: media-download-bot
description: Build or debug a Telegram yt-dlp downloader bot on Termux.
---

# Media Download Bot (Termux · yt-dlp · python-telegram-bot)

Telegram bot where users paste a video URL (YouTube/TikTok/IG/FB/X) and receive the
file back in-chat. Proven end-to-end in `~/media-dl` (bot.py + downloader.py).

## Stack & prerequisites

- python-telegram-bot v22, `yt-dlp` (`pip install -U yt-dlp`), `ffmpeg` (Termux pkg).
- ffmpeg MUST be passed to yt-dlp as an **absolute path**
  (`--ffmpeg-location /data/data/com.termux/files/usr/bin/ffmpeg`). A relative
  `"ffmpeg"` works interactively but silently skips merging when run under PM2 —
  the merged file never appears even though exit code is 0.

## Getting the output file reliably

Do NOT rely on `--print-json`: its top-level `filepath` and even
`requested_downloads` can be null on newer yt-dlp after merging. Use instead:

```python
cmd = ["yt-dlp", "--no-playlist", "--no-warnings",
       "-f", fmt, "--merge-output-format", "mp4",
       "--ffmpeg-location", FFMPEG_ABS,
       "-o", out_template,
       "--no-simulate", "--print", "after_move:filepath",
       url]
# stdout's last line starting with "/" and os.path.exists() == the final file.
```

Fallback if that line is missing: newest `*.mp4` in the download dir modified <5min ago.
After sending, delete fragments (`*.fNNN.mp4`, `*.m4a`) and the sent file — Telegram caps
uploads at ~50MB; check size before sending and error politely over that.

## Quality & MP3 selection UX

Don't auto-download: reply with an InlineKeyboardMarkup
(`🎬 480p / 🎵 MP3 / 🎬 720p / 🎬 1080p` encoded in callback_data like `d|<url>|720|v`)
and handle it in a `CallbackQueryHandler`. Format strings per quality:

```
bestvideo[height<=N][ext=mp4]+bestaudio[ext=m4a]/best[height<=N]/worst
```

MP3 = download merged mp4 first, then `ffmpeg -y -i in.mp4 -vn -b:a 128k out.mp3`,
delete the video. Send audio with `reply_audio`, video with `reply_video`
(read/write timeout 300).

## Free-tier limits

JSON file `{date, users:{chat_id:count}}`; reset counts when date rolls over.
Free limit ~5/day; premium IDs loaded from `premium.json`. Check BEFORE processing,
record AFTER successful send. `/premium` command explains upgrade (manual activation:
add chat_id to premium.json). Auto-cleanup downloads older than 30 min.

## Platform reality (as of 2026-08)

- YouTube: works well via yt-dlp.
- TikTok: yt-dlp extractor repeatedly breaks ("Unable to extract universal data");
  curl_cffi impersonation does NOT fix it. Fallback chain: tikwm.com API (also flaky)
  → tell user TikTok is temporarily broken rather than looping failures.
- Always `pip install -U yt-dlp` first when downloads suddenly fail.

## Deployment

Wrapper `start.sh` (cd + export BOT_TOKEN + exec python3 bot.py) → `pm2 start start.sh --name X`
→ `pm2 save`. Verify with `pm2 logs X --lines 8 --nostream` looking for getMe 200 +
"Application started". Tokens shared in chat should be revoked via @BotFather once stable.
