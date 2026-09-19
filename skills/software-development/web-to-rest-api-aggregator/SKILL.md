---
name: web-to-rest-api-aggregator
description: Use when turning scraped websites into a public REST API.
---

# Web → REST API Aggregator

Pattern for turning one-or-more websites into a clean public REST API with Express/Node, deployed to Vercel, with cache-first design and multi-source dedup. Proven on a 3-source comic API (~26 endpoints, live on Vercel).

## Workflow per new source

1. **Recon before scraping.** Determine what kind of site it is:
   - Next.js/RSC sites: data embedded in HTML as escaped JSON (`\"field\":\"value\"` payloads). No public REST — parse the payload with segment regexes.
   - WordPress/classic sites: parse HTML sections directly.
   - Full SPA (empty shell HTML): data loads client-side from a **hidden REST API**. Find it by downloading the JS bundles listed in the page (`_app/immutable/**` chunks for SvelteKit), then grep all chunks for `https://` URLs containing `api`. Real example: Shinigami's official `api.shngm.io/v1` was buried in a 96KB page-node chunk.
   - Also try `/sitemap.xml`, `/robots.txt`, `/wp-json/`, `/__data.json` (SvelteKit) quickly — cheap wins first.
2. **Write one scraper file per source** (`scraper/<site>.js`), never mix. Each exports `scrapeList / scrapeDetail / scrapeChapters / scrapeChapterImages`.
3. **Verify against the live site** before wiring endpoints: fetch the site homepage in the same request window and diff titles/chapters pairwise. Report match percentage.
4. Register routes in server + a serverless copy; add alias paths if desired.

## Hard-won rules (each was a real bug found in review)

- **Escaped-payload regex:** use `[^"]+` not `[^"\\]+` when capturing values that contain backslash escapes (`\u0026`) — the backslash class silently truncates matches and you lose most items.
- **HTML-entity URLs:** normalize `&amp;` → `&` in every extracted URL, or image/request URLs return 400/403 while looking fine as strings.
- **Signed S3 URLs:** covers/assets may be pre-signed (`X-Amz-Signature`, expires ~6 days). Plain bucket URL = 403. Store both a stable `coverPath` and `coverExpiresAt`; offer a resolver endpoint (`GET /cover/:id` → 302 to fresh signed URL).
- **Numeric chapter sorting:** always `parseFloat` compare, filter NaN (formats like `687-2` exist). String sort gives 1,10,100,11. Expose `firstChapter`/`lastChapter`/`missingChapters` — list length ≠ last chapter number.
- **Latest = timestamp, not chapter number:** a provider with chapter 112 updated later beats chapter 113 updated earlier. Sort by ISO timestamp; store chapter per-provider, never auto-pick the max number.
- **ISO timestamps over relative strings:** convert "2 jam lalu" → ISO at scrape time; expose both (`updatedAt` human, `updatedAtIso` machine). Sort DESC with NULLS LAST (nulls must not float to top of views/rating sorts).
- **Dedup across providers:** normalize titles (lowercase, strip punctuation/apostrophes including ’ ‛, collapse non-alphanumerics, strip `part\d+` suffix) then merge into one entry with `providers: { <source>: {chapter, updatedAt} }`. Report transparency meta: `totalRawItems`, `duplicatesRemoved`, `providerCounts`.
- **Views/stats null semantics:** `null` = provider has no stats; `0` is a real value. Don't coerce.
- **Status normalization:** providers say end/completed/complete — normalize to one internal schema at scrape time AND in query filters.
- **Pipeline order is law:** Filter → Sort → Pagination. Never paginate before filtering.

## Media-site patterns (hidden AJAX, image proxies, warm-up gates)

- **Image proxy with size-in-URL = free HD:** if thumbnails look low-res, inspect
  the URL — sites often serve images through a resizing proxy with dimensions in
  the path (`convert.d-cdn.me/convert/<base64url>/72x72/1.jpg`). The proxy
  usually accepts arbitrary sizes: rewrite `72x72` → `480x640` (poster ratio) at
  scrape time. Decode base64url payloads by stripping trailing `--`, then
  `-`→`+`, `_`→`/`, pad `=` (shell `tr '-_'` fails — do it in Python/JS).
- **Homepage cards often come from a hidden AJAX catalog:** near-empty homepage
  + `ajax`/`.php` strings in the HTML → endpoints like
  `POST /ajax/index_terbaru.php` with body `token=<token_now>` where the token
  sits inline in the homepage source (`var token_now = "..."`). Send
  `X-Requested-With: XMLHttpRequest` + `Referer`; a `"Token Not Found"` body
  means the token was missing. Cache the token ~10 min and re-fetch the homepage
  once on rejection. These endpoints return 10–25 rich cards vs ~5 static ones.
- **Catalog cards may use redirect links** (`/go/12345` → 302 → `/nonton/slug/`):
  resolve with `redirect: "follow"` and read `res.url`; keep resolving at the
  detail/episodes/sources layer or canonicalize the id to the real slug early.
- **Warm-up gate on player pages:** some sites serve the watch page WITHOUT the
  player unless the detail page was requested first (normal browsing flow).
  Response is 200 but iframe-free → sources come back empty. Fix: fetch the
  detail page (cached) as a warm-up before the watch page, and re-check the body
  for player markers (`bunny|player`) with one retry.
- **Burst throttling:** ~a dozen upstream hits back-to-back (audits!) can trip a
  minutes-long throttle that returns player-less pages — retries after seconds
  do NOT clear it, but a single request after minutes works. Mitigate: cache
  detail HTML ~60s, and in audit scripts test the throttle-prone endpoint FIRST.
  Before blaming the scraper, reproduce the site's own flow with curl (fetch
  detail, then watch with cookie jar) — if the live site serves no player for
  that item, it's upstream link-rot (dead legacy host, brand-new series without
  players yet), not selector rot.
- **Invisible search pagination:** even with no visible pager, try `&p=2` and
  merge results deduped by id — can multiply result count several times.
- **When counts stay small, ask the user for URLs they see:** a one-line link
  from the user (`/list/1`) revealed a site's REAL full catalog — ~33 items/page,
  2600+ titles, paginated — after every AJAX endpoint turned out to be a fixed
  ~15-item teaser (params ignored, byte-identical responses). Treat AJAX rails
  as previews; probe for a paginated static catalog (`/list/N`, `/page/N`,
  genre pages) and merge deduped.
- **One site, multiple card markups:** the same site can render different card
  structures per page type (`article.movie-list-card` on AJAX/search vs
  `article.trending-card` on its trending page — rank badge, no title attr).
  A selector set that works on one page can silently match ZERO on another, and
  `ok:true` hides it (trending returned 25 stale instead of 54). Verify item
  counts per source page after every extractor change.
- **Detail pages carry rich `Label: Value` metadata:** Director / Network /
  Episodes / Country / Duration appear as inline text rows — regex
  `>\s*Label[^<>]{0,5}:\s*value<` pairs off the HTML and normalize into typed
  fields. Derive status with heuristics when the site has no explicit one:
  episodes-released < episodes-total → ongoing; year < current year → completed.
- **Missing page types are common:** no "completed" listing at all (every
  candidate path 404)? Build it from the TAIL of the newest-sorted catalog
  (old entries ≈ finished) + per-title heuristics — and document honestly that
  it's derived, not scraped from a real page.

## Finding hidden endpoints: HAR capture beats JS archaeology

When a site's XHR endpoints are buried in obfuscated JS (string-array + hex-index
encoders, e.g. `a.js` full of `var _0x...=...`), stop grepping — ask the user for a
**HAR capture** (mobile devtools / browser network export) of them browsing the
detail page and playing one episode. That one file exposes the full API in
seconds:

- Parse `log.entries[]`: filter OUT images/fonts/css/js and `.m4s` segment
  streams; what remains is the endpoint set. Record method + URL + request
  headers (Origin/Referer/UA) + response bodySize.
- Replay endpoints with curl using the captured headers (Origin + Referer
  required for CORS).
- HAR bodies are often empty (0 chars) — that's fine, URL + headers suffice to
  reconstruct the calls.

Endpoint probing: **404 = no such endpoint, 500 = exists but wrong params,
200 = hit.** Once you know the host, brute a few plausible names
(`episode.php`, `episode_mob.php`, `list.php`) with a 1-param guess; 500 vs 404
tells you which to pursue.

Anti-leech params (`t`, `ver`, `c`, `token`) are frequently optional — test by
dropping them; the API often answers 200 with all data anyway.

Real example (drakor.kita.mobi, Aug 2026): HAR revealed `api.nonton.bid/c_api/` —
`episode.php?movie_id=<first-ep-id>` returns the full episode list (`data-epid`
links), `video.php?id=<epid>` returns per-episode streams + `next`/`prev` episode
ids + `hls_key`, `server_mob.php` lists server qualities. Full endpoint map in
`references/drakor-kita-mobi-endpoints.md`.

## Deobfuscating obfuscated site JS with a Node VM harness

When the endpoint builder is encrypted (string-array with per-index keys,
e.g. `_0x5451(idx,key)`), regex-extraction of strings fails — but you CAN run the
script in a Node `vm` sandbox with mocked browser globals, let it define its
functions, then call them / hook the network layer:

- Sandbox must provide: `window`/`globalThis`, `document` (getElementById etc.),
  `location` (+ `search`, `pathname`), `navigator.userAgent`, `innerWidth`/
  `innerHeight`, `setTimeout` (run fn synchronously), `atob`/`btoa`, and the
  `c_api_host`-style config vars you already learned from the HAR.
- Mock `$`/`jQuery` as a Proxy whose `.ajax` records `{method, url, data}` to an
  array you dump after load — every `.ajax`/`fetch`/`XHR` call becomes visible.
- After `vm.runInContext`, the script's top-level `function`s surface as sandbox
  globals (`loadEpisode`, `initEpisodeList`, `get_link`...) — call them directly
  to trigger the recorded ajax calls, or decode `get_link(url)`.
- Guard: the script may throw mid-load ("X is not a function") yet still define
  the functions you need — catch the error, inspect `Object.keys(sandbox)` for
  the targets, and proceed.

## Stream URL expiry & CDN chains

- API endpoints may be Cloudflare-cached for a year while the embed URLs they
  return expire in minutes (the embed page 404s right after `video.php` returns
  it fresh). "Fresh API response" ≠ "playable URL".
- Actual video often comes from a separate CDN: `video.php` → embed
  (`seniman1.uyeshare.cc/e/...`) → CDN (`1xmaza.drakor.bid/galeri/<mid[:2]>/
  <mid[2:4]>/<fileid>/init.mp4` + `out*.m4s` DASH segments, no .mpd/.m3u8). CDN
  segments outlive the embed URLs.
- `video_p2p.php` → P2P/WebTorrent page (`drakorkita.stream/#...`);
  `video_hydrax.php` → hydrax embed (`abysscdn.com/?v=...`). Both are alternate
  server paths worth exposing as `type: iframe` streams.

## Infra essentials (add these from day one)

- **CORS middleware** if the API is meant for browser clients — without `Access-Control-Allow-Origin` every localhost call gets blocked ("kena begal CORS"). In Express serverless, remember the app variable name (`api.use`, not `app.use`) — wrong identifier compiles fine locally but 500s on deploy.
- **Rate limiter** (per-IP window counter, OPTIONS exempt) — document it honestly in your docs page and enforce it.
- **Health check per source** on a timer (`/api/health` reporting each upstream's ok/error/lastCheck).
- **Cache-first with disk persist**: RAM map + TTL per endpoint type (lists short, images long), persisted to JSON every few minutes and on SIGTERM so restarts aren't cold.
- **PM2 + boot script + `pm2 save`** for always-on local hosting; Vercel for public hosting.

## Vercel deployment pitfalls

- Serverless function crashes show only as `FUNCTION_INVOCATION_FAILED` — test each route after deploy, don't assume parity with local.
- Wrong variable name in middleware (`app.use` vs `api.use`) works locally but 500s remotely — grep before deploying.
- If scrapers live in sibling dirs, add `"includeFiles": "scraper/**"` to the builder config or requires fail in the bundle.
- Static pages 404ing while API works: routing order in `vercel.json` — explicit page routes must come before the catch-all static rewrite.
- New deploys may serve stale alias domains briefly; verify against the fresh deployment URL, and `vercel promote` if needed.
- Vercel Authentication (SSO) makes curl get redirect-to-SSO pages: disable via `PATCH /v9/projects/<name>` with `{"ssoProtection": null}`.

## Review culture

Iterate with the user using structured reviews (they paste response JSON back). Common findings worth pre-empting: mixed-up field pairing between title/chapter/time, inconsistent rank ordering, missing dedup, misleading counts. Always cross-check API output against the source site's live state before claiming correctness.
