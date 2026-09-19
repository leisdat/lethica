# Media scraper extension patterns (otakudesu / anichin case studies)

Session-verified patterns for scraping Indonesian anime/donghua sites into
Extension Hub Pro extensions. All tested live against real sites.

## Site recon workflow (do this before writing any scraper)
1. `curl -sL <url> -H "User-Agent: Mozilla/5.0 ... Mobile" -o /tmp/page.html -w "%{http_code} %{size_download}b"`
2. `grep -oE 'class="[^"]*"' page.html | sort | uniq -c | head` — find list-item classes
3. Extract one full item block and read it raw — identify: link, title element, poster img, episode/rating badges
4. For player pages: check `<iframe>`, `<option value=...>` (often BASE64 iframes), direct .mp4/.m3u8 in page source
5. Check detail page for info fields (`<b>Skor</b> : 7.20` style key-value lists)

## Verified site structures

### otakudesu.blog
- Home/on-going/complete: `li > div.detpost` → `.epz` (Episode N), `.epztipe` (rating OR day), `.thumb a[href*=/anime/]`, `img`, `h2.jdlflm`
- Search & genre pages: `ul.chivsrc li` → `h2 a` + `img`
- Detail: `.infozingle p:contains('Judul')`, genres via `p:contains('Genre') a`, status/score/type/duration as `<b>Skor</b> : value` (NOT plain text — selector needs `p:contains('Skor') b` or regex on parent text)
- Episode page: iframe = desustream lazy player; resolve DIRECT MP4 by fetching the iframe URL and regexing `https?://...\.mp4` from its source (lazy player embeds videoURL in JS). Mirrors: `div.download ul li` → `<strong>Mp4 480p</strong>` + multiple host links + `<i>size MB</i>`
- `/anime-list/` has NO posters (text-only index). Use `/ongoing-anime/` + `/complete-anime/` for poster-bearing catalogs.
- Titles are dirty: strip `(Episode N – M)`, `Subtitle Indonesia`, `Batch` suffixes via cleanTitle().

### anichin.cafe
- Lists everywhere: `article.bs > .bsx > a.tip[title]` + `.limit img` + `.tt` (series name is first text node, h2 inside = episode title) + `.typez` (Donghua/Movie) + `.epx` (Ep N)
- Detail: `/seri/{slug}/`; h1.entry-title, `.mgen a` genres, `.entry-content p` synopsis
- Episodes: `.eplister ul li a` with `-episode-N` slug
- Sources: dropdown `<option value="BASE64">ServerName</option>` — decode base64 → extract `src="..."` from iframe HTML → that's the embed URL (OK.ru, Dailymotion, Rumble, abyssplayer...)
- Catalogs are query-based: `/seri/?status=&type=&order=popular`, `?status=Completed`, `?type=Movie` (no /donghua/ or /popular/ paths — those 404)
- Genres at `/genres/{slug}/`; the full genre list (~45 links) lives on the HOMEPAGE (`a[href*='/genres/']`) — not on /donghua/ (404) or a genre index page
- Schedule `/schedule/`: day blocks `.bixbox.schedulepage` → day name in `h3 span` (ENGLISH: Monday..Sunday) → items `.bsx a[href*='/seri/']` with title in `.tt` and release time in `.epx` (e.g. "at 04:45"). Map EN day names → Indonesian in the scraper (Senin..Minggu)

### drakorid.co
- Detail/watch: `/nonton/{slug}/`; slugFrom strips only the origin (ids are bare slugs, unlike anichin's `seri/...` prefix)
- Catalogs: `/drama-ongoing/`, `/drama-populer/`, homepage rails; genres from `/kategori.html` → `a[href*='/kategori/']` (name = `.in` text minus `.badge` count)
- Schedule `/jadwal.html`: day TAB BUTTONS carry `data-dow` but the CONTENT PANELS use `data-panel="1..7"` (Senin..Minggu order) → select `[data-panel="${dow}"]`, items `a[href*='/nonton/']` with `.jdw-card-title` + time badge `.jdw-card-time-badge`. Selecting the tab attribute returns zero panels.

## Sections capability (dynamic Home)
Extension declares optional caps `sections` + `section`:
- `sections()` → [{id, name, type: list|schedule|genres}]
- `section(id)` → poster list items (with title/thumbnail) OR schedule rows [{day, items}] OR genre list [{id, name}]

Host aggregates: UI asks each enabled section-capable extension for its sections,
renders one carousel per (source × wanted-section-id), removes carousels that come
back empty or non-poster. IDs like `genre:<slug>` parametrize sub-content.

## Pitfalls hit this session
1. **Duplicate function declaration kills feature**: adding a new `renderDownloads`
   while an old placeholder version remained later in the same inline script — JS uses
   the LAST declaration, so users saw "NOT IMPLEMENTED" despite working backend.
   Grep for `function X` count == 1 after editing big inline-script HTML files.
2. **Endpoint unreachable**: placing `/downloads/:file` handler inside `handleAPI()`
   which only runs for `/api/*` prefixes — every request 404'd via the static-file
   fallback. Non-API routes must be handled at the top-level request router.
3. **Circular JSON crash**: persisting job objects holding `_req`/`_ws` (http client +
   stream) crashes `JSON.stringify`. Destructure out internal props before saving:
   `jobs.map(({_req,_ws,...rest}) => rest)`.
4. **encodeURIComponent on slugs**: slugs may contain `/` (e.g. `seri/perfect-world`);
   encoding turns it into `%2F` → 404. Slugs from your own parser are URL-safe; pass raw.
5. **Video serving needs Range support**: browsers send `Range: bytes=N-` when seeking;
   respond 206 + Content-Range + stream slice, else seek breaks.
6. **Mini-player handoff**: on sheet close, if a `<video>` exists and is not paused,
   move src+currentTime to a fixed-position mini element instead of destroying playback;
   expand reverses the handoff using cached episode context.
7. **Attribute/structure drift breaks scrapers silently**: selectors written from an
   OLD layout keep "working" (no throw) but return 0 items → API returns `[]` with
   `ok:true`, so nothing looks broken until someone opens the page. Real cases:
   drakorid jadwal redesigned panels to `data-panel` while code read `data-dow`
   (tab buttons only); anichin schedule selectors guessed `.schedule-item` etc. and
   matched nothing. Audit scrapers by asserting NON-EMPTY output per capability —
   `ok:true` + `n=0` IS a failure. Workflow that found all bugs in one pass:
   fetch the live page → locate one real day/genre block in raw HTML →
   read exact classes/attrs → rewrite selector → re-verify via API count.
