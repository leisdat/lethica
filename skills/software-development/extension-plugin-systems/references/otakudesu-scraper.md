# Real scraper extension: otakudesu.blog (worked example)

Anime scraper extension built for Extension Hub Pro. Site is public (no DRM/auth),
same category as the komiku scraper already used in the Xyra project — OK to scrape,
but it hosts licensed anime so keep it technical/portfolio use.

## Page-structure discovery workflow
Never guess selectors — fetch the page and grep for structural classes first:
```bash
curl -s -L "https://otakudesu.blog/" -H "User-Agent: Mozilla/5.0 (Linux; Android 13)" \
  -o ~/tmp/otaku.html; grep -oE 'class="[^"]*(detpost|chivsrc|venz|jdlbar)[^"]*"' ~/tmp/otaku.html | sort | uniq -c
```
Then dump one block's raw HTML to see field layout. Each page type has a DIFFERENT
structure — do not reuse the homepage selector on search results.

## Selector map (verified)
| Page | URL | Selector |
|---|---|---|
| Home (on-going) | `/` | `ul li .detpost` — `.epz` (Episode N), `.epztipe` (day), `.newnime` (date), `.thumb a img`, `h2.jdlflm` |
| Search | `/?s={q}&post_type=anime` | `ul.chivsrc li` — `h2 a`, `img` |
| Detail | `/anime/{slug}/` | `.infozingle p` (info), `.sinopc` (sinopsis), `.fotoanime img`, `.episodelist ul li` |
| Full list | `/anime-list/` | `.jdlbar ul li a.hodebgst` (NO thumbnails) |
| Episode | `/episode/{slug}/` | `iframe` (player), `a[href*="desustream"]` (mirrors) |

Detail info rows are `<b>Skor</b> : 7.20` — NOT `p:contains('Skor')` text; use
`$(".infozingle p:contains('Skor') b").parent().text()` to capture the value.

## Title cleaning (regex, applied to all title extracts)
Raw otakudesu titles carry suffixes: `#Compass 2.0: Sentou Setsuri Kaiseki System
(Episode 1 – 12) Subtitle Indonesia`. Strip in order:
```js
t = t.replace(/\s*\(?\s*(?:Episode|Eps)[^)]*\)?\s*$/i, "");            // (Episode ...)
t = t.replace(/\s*[-–—]?\s*(?:Subtitle Indonesia|Sub Indo|Batch|Complete)\s*$/i, "");
t = t.replace(/\s*\(?(\d+\s*[-–—]\s*\d+)\)?\s*$/i, "");                // (1 – 12)
```

## Extension methods beyond the 4-contract
`latest(limit)` scrapes the homepage (on-going anime with episode labels) — this is
what feeds the Home "Update Terbaru" feed. `trending(limit)` scrapes `/anime-list/`
(full catalog, but no thumbnails → UI must render a gradient-initial placeholder
for empty posters, not a broken img). `genres()` + `byGenre(id, page)` for browse.
Declare these in manifest `capabilities` so the aggregator's `latest()` prefers
them over `search("")`.

## Stream extraction
Episode page yields 1 player iframe (blogger) + many mirror links (desustream
redirects: Zippy, Hxfile, Racaty, Mega...). Group UI-wise: Player (iframe/embed)
vs Mirror/Download (url). Iframes need `src.replace(/&amp;/g, "&")`.

## Soft-fail tests
Real-site tests must not break the suite when the site is down: run the worker
call, and if `!res.ok` log a warning and `return` (skip) instead of asserting.
