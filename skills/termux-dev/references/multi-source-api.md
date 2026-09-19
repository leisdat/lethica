# Multi-source expansion & sorting correctness (komiku.org case, verified 2026-08-24)

Continuation of the VoraToon single-source API (`~/voratoon-api/`, Express :3000).
Adding a second comic site (komiku.org) and fixing "latest" ordering.

## Second site = classic server-rendered HTML (not RSC)
Different parsing pattern entirely:
- Homepage sections carry the data: `<article class="ls2">` = latest updates (includes
  relative time "N menit lalu" + latest chapter link); popular lives in
  `id="rank-{mingguan|harian|total}"` panels with `<article class="ls4">` items
  (rank-num, genre · views). Split by article boundaries with matchAll — don't attempt
  one mega-regex across sections.
- Search runs through a separate internal host: `api.komiku.org/?s=q` returning `.bge`
  blocks. Manga slug = first href in block minus trailing `-chapter-N`. Also probe
  `wp-json/wp/v2/search?search=` — some WP sites expose it.
- Chapter page images on a plain CDN host (`image2.komiku.to/upload5/...`) — filter out
  promo/asset images by URL substring before dedup.

## Express route-order pitfall
`GET /api/komiku/:slug` registered BEFORE `/api/komiku/search` swallows the literal path
(request hits detail handler with `:slug='search'` → weird upstream 404). Register all
static literal segments before parameterized ones.

## Frontend multi-source normalization
Each source returns a different item shape. Normalize in JS right after fetch using the
envelope flag (`source: 'voratoon'|'komiku'`), keep one `curSrc` variable driving tabs,
search endpoint choice, detail route, and reader route:
- voratoon: `/api/series/:slug`, images at `/api/series/:slug/chapter/:num`
- komiku: `/api/komiku/:slug`, images at `/api/komiku/:slug/chapter/:num`
User wanted visible provenance — colored badges showing active API ("muncul rest api
komiku gitu biar bagus"): brand title/subtitle swap + badge on detail page and in the
reader header, footer credit line for both sources.

## Combined endpoint
`/api/all/latest` via `Promise.allSettled` over both cached scrapers → one response with
both sources; degrades gracefully if one site dies (fulfilled-only).

## Sorting correctness ("latest" must be REAL)
Homepage render order ≠ update order — user caught fake ordering ("masih acak cek lagi
bener bener takut salah"). VoraToon RSC payload embeds per-chapter `createdAt`
timestamps; extract max(createdAt) per series segment and sort `/latest` by it
(fallback rating). For popular use real payload signals (views/bookmarkCount), not just
rating. Expose `latestChapterAt` in responses so clients can show "3j lalu" chips.

## Regex-in-JS-files workflow lesson
Writing complex regex into JS files via patch tools kept failing on escape-drift and
double-backslash drift (JS regex `\\"` vs file content `\\\\\"`). What worked:
1. Prototype the regex against saved HTML with a small standalone node script first.
2. When writing into the target file, generate the line from python using
   `chr(92)` repetition instead of hand-counting backslashes.
3. Character-class subtlety: `[^"\\]+` breaks on URLs containing `\u0026` escapes —
   use `[^"]+` and clean up after; verify match counts against a known total (96
   occurrences / 67 unique) before trusting it.
4. Cache invalidation after scraper changes: kill + restart the node server, or stale
   cached data masks your fix.
