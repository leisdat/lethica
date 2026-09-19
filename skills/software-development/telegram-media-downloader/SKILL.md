---
name: telegram-media-downloader
description: Build Telegram media-download bots in Termux with yt-dlp.
---

# Telegram Media Downloader Bot (Termux)

Pattern for bots where users paste video links and the bot downloads and sends the file
back. Proven with the user's `~/media-dl` bot (YouTube tested end-to-end; TikTok/IG/FB
via the same yt-dlp engine).

## Stack

- python-telegram-bot v22 (`Application`, `CommandHandler`, `MessageHandler`,
  `CallbackQueryHandler`, `InlineKeyboardButton/Markup`)
- `yt-dlp` (supports 1000+ sites) + `ffmpeg` for stream merging and MP3 extraction
- JSON usage ledger (`usage.json` keyed by date) for daily free-tier limits;
  `premium.json` = list of premium chat_ids

## Flow that converts users

1. User pastes a URL → bot replies with an **InlineKeyboard** of format choices
   (Video 480p / 720p / 1080p / MP3) via `callback_data=f"d|{url}|{quality}|{mode}"`.
2. CallbackQueryHandler splits on `|`, checks the daily limit, edits the status message
   ("⏳ Downloading…"), runs the download in an executor, sends back with
   `reply_video`/`reply_audio` (pass generous `read_timeout=300`).
3. Free tier = N downloads/day (`usage.json` reset per date); premium unlimited.
   Always tell the user their remaining quota after each download.

## yt-dlp pitfalls (all hit in practice)

- **Modern YouTube serves DASH**: video and audio are separate streams. Format string
  must merge them:
  `bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]/worst`
  with `--merge-output-format mp4`. A plain `best[height<=480]` selector often errors
  "Requested format is not available".
- **Always use ABSOLUTE path for `--ffmpeg-location`.** A bare `"ffmpeg"` works from an
  interactive shell but silently skips merging when run under PM2/background context —
  exit code stays 0, fragments (.fNNN.mp4/.m4a) are left behind, and no merged file ever
  appears. Symptom: `--print after_move:filepath` prints a merged path that does not
  exist on disk. Fix: `/data/data/com.termux/files/usr/bin/ffmpeg`.
- **Get the final filepath via `--print after_move:filepath`**, not `--print-json`:
  newer yt-dlp emits metadata JSON whose `requested_downloads` may be null. The
  after_move line is printed last on stdout and is the real post-merge location.
- After sending, delete the downloaded file AND any leftover `.fNNN.*`/`.m4a` fragments
  matching the same output timestamp prefix (mobile storage fills fast).
- Enforce a size cap (~45MB) — Telegram bot upload limit. Check before upload and give a
  human-readable error.
- Platform-specific extractors break periodically (e.g. TikTok "Unable to extract
  universal data"). Design a fallback chain: yt-dlp → third-party API (tikwm etc.) →
  honest "this platform is temporarily broken" message. Keep `pip install -U yt-dlp`
  as routine maintenance.

## Deployment

PM2 wrapper script (`start.sh`: cd + export token env + TERM=dumb + exec python3),
`pm2 start ./start.sh --name <bot> && pm2 save`. Token rotation = edit start.sh +
`pm2 restart`. See telegram-llm-bot skill for the multi-instance Conflict pitfall.
