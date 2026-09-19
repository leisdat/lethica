# Multi-source comic API — Vercel serverless + reader bugs (Xyra case, verified 2026-08-25)

Continuation of the multi-source comic API (`~/voratoon-api/`, 3 sources: voratoon RSC,
komiku HTML, shinigami official REST `api.shngm.io/v1` with mandatory `Origin` header).
Live at https://xyra-api.vercel.app (rebrand from voratoon-api; old domain died).

## Serverless deployment (Vercel) pitfalls
- Mirror EVERY new route from `server.js` into `api/index.js` — forgetting causes
  mysterious 404s that work locally. This caused 3 separate production bugs.
- `includeFiles: "scraper/**"` in vercel.json builds is REQUIRED or scraper modules
  crash (`FUNCTION_INVOCATION_FAILED`).
- Route order matters: register specific paths (`/api/shinigami/latest`, `/genres`)
  BEFORE parameterized (`/:mangaId`) or they get swallowed.
- `functions` and `builds` properties in vercel.json are MUTUALLY EXCLUSIVE —
  cannot set maxDuration while using builds. Use `builds.config` only.
- Vercel SSO Protection blocks anonymous curl with an SSO redirect page; disable via
  REST: `PATCH /v9/projects/<name>` body `{"ssoProtection": null}`.
- Alias can point at a deleted deployment → `DEPLOYMENT_NOT_FOUND`; re-deploy or
  `vercel promote <deployment-url>`.
- Serverless instances are cold-started per request region: RAM cache does NOT persist
  across invocations like PM2. Cache keys must be self-healing (re-fetch on miss).

## cached() wrapper contract (source of a subtle bug)
`cached(key, ttl, fn)` returns `{data, ts}` — NOT the raw data. Every caller MUST
destructure `const {data} = await cached(...)`. A player-images route assigned the
wrapper object directly to an array variable → `.length === undefined` → permanent
404 "chapter tidak ditemukan" despite upstream being fine. Symptom: route matched,
JSON error response returned, only that one route broken.

## Reader "gambar kepotong" debugging saga (multiple root causes stacked)
User reported chapter images cut off / not scrollable FOUR times before all causes fixed:
1. **Preview contamination**: source site's chapter HTML embeds preview images from OTHER
   (newer) chapters alongside the requested one. Filter image URLs by folder segment
   matching the requested chapter (`/${chapter}/` regex test), THEN dedup.
2. **Dual URL formats**: same site uses `imageN.komiku.to/upload5/...` (new chapters) AND
   `imageN.komiku.to/wp-content/uploads/NNNN-1.jpg` (old chapters). Regex must match both
   or older chapters return empty → "tidak ditemukan". Audit multiple chapters across the
   age range, not just the newest.
3. **lazy-loading inside scroll container**: `<img loading="lazy">` inside a scrollable
   div never triggers intersection observer on mobile Chrome → images below fold never load.
   Remove lazy for reader pages.
4. **body overflow:hidden blocking nested scroll**: setting `document.body.style.overflow=
   'hidden'` when opening an overlay ALSO kills scrolling inside position:fixed children
   on Android Chrome. Final working pattern: NO fixed overlay at all — reader is a normal
   in-flow block (`position:relative`, no inset/fixed/height caps), hide `<main>` instead,
   let BODY do the native scrolling. Images: `width:100%; height:auto; object-fit:contain`,
   never `height:100vh/100%/object-fit:cover`.
5. **Missing element id crashes handler**: `$()` = getElementById; renaming markup without
   adding `id="main"` made `$('main').style` throw TypeError inside openCh → reader never
   opened. Verify every `$('id')` has a matching `id=` in HTML after refactors.

## Frontend polish that landed well
- Skeleton shimmer placeholders instead of spinners; cover fade-in via onload class.
- 🔥 NEW badge when latestChapterAt < 60 min; verbose relative times ("18 menit lalu").
- Chapter list as full-width ROWS with BARU badge on top-2 recent + estimated dates
  (interpolate backwards from latest update), not tiny number grid.
- Unified feed from `/api/all/latest` (dedup by normalized title, providers{} map),
  filter chips (Terbaru/Populer/Rating/Completed/format) hitting query params.
- Genre dropdown panel (30 genres) filtering `/api/all/browse?genre=`.
- openCh fallback chain: try komiku endpoint then voratoon endpoint (or reverse) —
  feed may report a chapter number from either source.

## Telegram AI-browser bot companion (`~/ai-browser/`)
python-telegram-bot v22 + httpx/bs4 engine + LLM via `hermes chat -q "<prompt>" -Q`
(subprocess; -Q for quiet output, strip Session:/Title:/Duration:/Messages: lines).
Playwright is NOT installable on Termux (no matching distribution) — requests+BS4 covers
most sites. Commands: /browse /ask /search /links /read /research /monitor /audit
/translate /news /define /calc. Monitor loop as asyncio task via `app.post_init`;
monitors persisted to JSON survive restarts. Only ONE bot instance may poll getUpdates
simultaneously (Telegram Conflict error) — pkill stale `bot.py` processes before restart;
pgrep matches its own shell wrapper, check with `pgrep -f "python3 bot.py"`.
Hermes OAuth tokens live in ~/.hermes/auth.json with 1h expiry & auto-refresh — do NOT
copy them into other tools; shell out to hermes CLI instead.