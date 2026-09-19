# Scraping Next.js RSC sites → REST API (VoraToon case study, verified 2026-08-24)

Working project: `~/voratoon-api/` (Express, port 3000). Source: `https://v1.voratoon.com`.

## Recon pattern (do this first)
1. `curl -sL -A "Mozilla/5.0 ..."` the homepage to a file. Next.js App Router sites embed
   all data in RSC payload scripts (`self.__next_f.push([1,"..."])`) — no public API needed.
2. Probe candidate endpoints (`/api/series`, `/api/comics`, ...) — most return 404; don't
   waste time, go straight to HTML/RSC parsing.
3. Grep the saved HTML for data shapes: `"slug":"..."`, `cover/`, `synopsis`, chapter href
   patterns (`/series/{slug}/chapter/N`). Chapter page images often come from a plain CDN
   (`cdn.voratoon.com/wp-content/img/...jpg`) with NO signing — easy win.
4. Metadata also hides in `<meta name="keywords">` — VoraToon packs title + genres there as
   a comma list (genres = items after the author entry ending in "comics", before "baca …").

## Critical: S3 signed cover URLs
Cover/background images are S3 presigned. Plain URL → 403 Forbidden.
Required URL shape (all params present, in order):
`...webp?X-Amz-Algorithm=...&X-Amz-Credential=..%2F..&X-Amz-Date=..&X-Amz-Expires=518400&X-Amz-Signature=..&X-Amz-SignedHeaders=host&x-amz-checksum-mode=ENABLED&x-id=GetObject`
Pitfalls:
- The final `&x-amz-checksum-mode=ENABLED&x-id=GetObject` is MANDATORY — without it S3
  returns 400 Bad Request even with a valid signature.
- In RSC payload the URL is HTML-escaped: `\u0026` and `&amp;`. Must unescape BOTH or you
  get 400. Fix: `.replace(/&amp;/g,'&')` after your generic unesc.
- Extract full signed URLs directly from payload via regex ending at `x-id=GetObject`;
  never rebuild from the bare path.
- Expiry ~6 days; cache TTLs must be well under that so re-scrape refreshes signatures.

## Regex-over-RSC technique
JS regex literals with escaped quotes get mangled by patch tools (escape-drift errors).
Reliable approach: build patterns with `new RegExp('\\\\\\"slug\\\\\\":\\\\\\"(...)')` strings,
and when a literal is unavoidable write it simple (`/"totalChapters":"?([^,"]+?)"?,/`).
If patching fights you, use a python script over the file to do exact string replacement.

## Cache-first API design (survives source-site death)
RAM Map cache keyed per resource with tiered TTL: home 10m / detail 30m / chapter images 6h.
All reads served from cache when warm → upstream outage degrades freshness only, not availability.
Response envelope `{status:'success', page, total, totalPages, data}`; paginate server-side (max limit 50).

## Endpoint set that worked
`GET /api/series?page&limit[&format&status]`, `/api/series/latest`, `/api/series/popular`
(sort by rating client-side), `/api/search?q=`, `/api/series/:slug`,
`/api/series/:slug/chapters`, `/api/series/:slug/chapter/:num` (image array),
`/api/stats`, plus docs at `/`.

## Comic-reader frontend on top of the API
Serve a single-file HTML from Express (`app.get('/comic', sendFile)`). Tabs filter via
querystring, grid of cards (cover+rating badge+format chip), detail view with poster/
stats/genre chips/chapter grid, fullscreen reader that lazy-loads page `<img>`s.
Test every endpoint with curl before telling the user the UI works.
