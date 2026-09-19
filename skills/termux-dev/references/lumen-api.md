# Lumen REST API — endpoint notes (verified live 2026-08)

Base: `https://www.v1lumen.my.id` — manga aggregator API (Indonesian providers, e.g. voratoon).
All responses wrap payload in `{status, message, data}`; read `j.data`.

- `GET /api/series?take=24&page=1&mode=newest&takeChapter=3&includeMeta=true`
  - `title=` query for search; `takeChapter` embeds latest chapter numbers per series;
    `includeMeta` adds synopsis/genres/rating.
  - Series item shape: `{data: {title, nativeTitle, slug, coverImage, backgroundImage,
    synopsis, status, format, rating (0-10), author, totalChapters, isHot,
    genres: [{data:{name}}], chapters:[...]}}`.
- `GET /api/series/{slug}` — full metadata for one series.
- `GET /api/series/{slug}/chapters` — list; items have `chapterIndex`, `data.title`,
  views. Sorted newest-first.
- `GET /api/series/{slug}/chapters/{n}` — reader pages; `data.images` = array of
  direct image URLs.
- `GET /api/genres` — taxonomy `{id,name,slug}`.
- `GET /api/popular?take=30&page=1` — ranking proxy.

Quirks:
- Cover URLs are signed S3 links with ~6-day expiry (`X-Amz-Expires=518400`) — cache
  them short-term, expect eventual re-fetch.
- Chapter `images` may be empty on the newest entries (drafts) before pages are pushed.
- CORS is open; a static single-file HTML app can call it directly from the browser.

Consumer pattern used by LUMEN-Comic.html (in user's home): normalize every item via a
`seriesOf()` helper because shapes differ between /series, /popular, and detail endpoints.
