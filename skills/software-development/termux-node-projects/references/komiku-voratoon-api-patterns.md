# Komik scraper-to-REST-API patterns (Termux, Express)

Validated 2026-08-24 building `~/voratoon-api` (multi-source comic REST API:
v1.voratoon.com + komiku.org). Class-level patterns for scraping a comic site
and serving it as a cached public JSON API.

## Source-site reconnaissance order

1. Try obvious REST endpoints first (`/api/series`, `/api/comics`, `/api/popular`) —
   most Next.js comic sites expose none; expect 404s.
2. Next.js App Router sites bake data into the HTML as an RSC payload
   (`self.__next_f.push(...)`) — data IS in the HTML, just escaped.
3. WordPress-era sites (komiku.org) serve plain HTML with stable class names —
   regex per `<article>` blocks is fine.
4. Check for microdata (`itemprop="genre" content="..."`) before writing fragile
   selectors — komiku.org exposes genres/status/type this way and it never breaks.

## RSC payload parsing pitfalls

- Escaping is multi-layer: fields appear as `\"slug\":\"value` in the raw HTML.
  When testing a regex against saved HTML in Node vs Python, backslash counts
  differ — verify match counts in BOTH or you'll "fix" the wrong layer.
- Character-class bug that cost an hour: `([^"\\]+)` truncates at the first
  backslash inside URLs containing `\u0026` escapes. Use `([^"]+)` then unescape
  after. Symptom: only ~12 of 96 blocks matched.
- Cover images on S3-backed sites are SIGNED urls (`X-Amz-Signature`,
  `X-Amz-Expires`). Plain bucket URL = 403. Extract the FULL signed URL including
  trailing params like `x-id=GetObject` — omitting it gives 400. Also decode
  `&amp;` → `&` or the signature check fails.
- Signed URLs expire (~6 days). Cache layers must refresh well inside that window.

## Correct "latest updated" ordering

Homepage render order ≠ update order. Real ordering requires per-item chapter
timestamps. Two working sources:
- Payload contains `chapters[].createdAt` per series → take max per slug,
  sort desc by ISO date.
- Or the site shows relative time ("25 menit lalu") → convert to ISO with a
  minute/hour/day/month multiplier table so clients can sort.
Verify by diffing API output against the site's own visible list — pairing bugs
(title from item N, chapter from item N+1) look "random order" to users.

## Cache-first architecture

- RAM Map cache keyed by string, TTL per data volatility:
  listing 5-10m, detail 30m, chapter images 6h, fast-moving feeds 5m.
- Benefit beyond speed: if the source site dies, the API keeps serving last
  known data (user explicitly valued this).
- Response envelope on every endpoint: `{status:"success", source:"<site>", ...meta, data}`
  so consumers know provenance when multiple sources exist.

## Multi-source layout

One scraper file per source (`scraper/<site>.js`) exporting the same function
names (scrapeLatest/scrapeDetail/scrapeChapter/scrapeSearch). Server routes
namespaced `/api/<site>/...`; optional merged endpoint uses Promise.allSettled
so one dead source doesn't kill the combined response.

## Frontend pair

Ship two static pages served by the same server:
- `/comic` reader UI (tabs per source, detail page, fullscreen image reader)
  — badge which source/API each view uses; users notice and value it.
- `/test` docs+tester page styled like public API docs (hero, blue CTA card,
  red RATE LIMIT warning box, green CATATAN box, Featured Endpoints cards,
  per-source endpoint sections with prefilled inputs and Send buttons).
User's taste: dark theme, professional/non-generic ("jangan pasaran"),
responsive mobile-first; wants source attribution visible in UI.

## Verification loop

- `node --check scraper/x.js && node --check server.js` before every restart.
- Cross-check scraped pairs (title/chapter/time) against ground truth parsed
  independently from saved HTML — catches pairing drift immediately.
- Kill old process (`pkill -f "node server.js"`), restart background, curl each
  endpoint group; a stale server silently serves old scraper code otherwise.
