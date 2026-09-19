# Phone Vault Pro — session addendum (2026-08-24)

## yt-dlp SABR round 2: `formats=missing_pot`
The 2026-08-23 fallback (`player_client=android` alone) broke again within a
day: `Only images are available for download. Requested format is not
available` + SABR warning. Fix that verified on real videos
(`8iuLXODzL04` YOASOBI 7.99MB, `t29k5FBkybk` 24.76MB, both exit:0):
append `formats=missing_pot` to EVERY client's extractor-args:
```
--extractor-args "youtube:player_client=android;formats=missing_pot"
```

## Timeout sizing
90s per attempt was too short for a 25MB video on mobile data → user-visible
`Timed out`. Raised to **240s per attempt**. Rule of thumb: ~10s per MB × 3
client attempts.

## Markdown escape must include `~`
ParseMode.MARKDOWN_V1 also chokes on `~` in filenames (strikethrough). Full
escape used in list/search lines:
```python
def esc(s): return s.replace("`","'").replace("*","").replace("_"," ").replace("[","(").replace("]",")").replace("~","-")[:42]
```

## Patch-tool backslash pitfall
Editing bot.py f-strings containing `\n` with the `patch` tool fails with
"Escape-drift detected" (JSON double-escaping). Workaround that worked:
use execute_code/terminal with a Python heredoc doing literal
`t.replace(old, new); p.write_text(t)` — no escaping issues.

## Dashboard thumb endpoint gotcha
Thumbnail endpoint must accept document JPGs, not only `type=="photo"` — most
of this user's photos are stored as documents. Check by extension too:
```python
is_img = f["type"]=="photo" or name.endswith((".jpg",".jpeg",".png",".webp",".gif"))
```

## VoraToon (v1.voratoon.com) recon for comic-API project
- Next.js App Router site; data embedded as RSC payload in HTML.
- NO public REST API: /api/series, /api/comics, /api/popular etc all 404.
- Scrapeable: `/series/{slug}` (detail), `/series/{slug}/chapter/{n}` links,
  homepage series list with ranking/hot flags. Parse RSC payload from HTML.
- Images are S3 signed URLs (`cvr.voratoon.id`, X-Amz-Signature, ~6-day
  expiry) → hotlinking is temporary; re-host if permanence needed.
- Plan if user proceeds: scraper + cache-first SQLite/JSON REST API so source
  death doesn't kill stored data (matches user's stated concern).
