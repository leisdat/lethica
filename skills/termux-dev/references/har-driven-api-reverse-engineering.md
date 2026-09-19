# Reverse-engineering a site's private API from a DevTools HAR

When a site loads its real content through JS (obfuscated `a.js`, `loadEpisode()`-style
onclick handlers, no data in the fetched HTML), **do not deobfuscate the JS**. That path
burned a long session here with zero yield: string arrays were hex-indexed, the entry
function needed globals (`c_api_host`) that only exist in the live page, and VM harnesses
with mocked `fetch`/`$.ajax`/jQuery never fired because the call is user-triggered.

The fast path is a **HAR file from the user's own DevTools** plus curl replay.

## 1. Ask the user for a HAR

"Buka DevTools → Network → mainkan/klik fitur yang dimaksud → klik kanan → Save all as HAR."
One HAR replaces hours of static analysis: it contains every request the page actually made,
with full headers.

## 2. Enumerate requests, ignore assets

```python
import json
h = json.load(open('file.har'))
for e in h['log']['entries']:
    u = e['request']['url']
    if any(u.endswith(x) for x in ('.png','.jpg','.css','.woff','.svg')):
        continue
    print(e['response']['status'], e['request']['method'], u)
```

Look for the API host — it is often a **different domain** than the site
(e.g. site `drakor.kita.mobi`, API `api.nonton.bid/c_api/*.php`).

## 3. Expect empty response bodies

HAR exports frequently omit `content.text` (or truncate it). Don't conclude the endpoint
returns nothing. Take the URL + headers and **replay with curl**, carrying over the headers
the browser sent — most importantly `Origin`, `Referer`, and the exact `User-Agent`:

```bash
UA="Mozilla/5.0 (Android 13; Mobile; rv:144.0) Gecko/144.0 Firefox/144.0"
curl -s --max-time 15 -A "$UA" \
  -H "Origin: https://site.tld" -H "Referer: https://site.tld/" \
  "https://api.host/c_api/video.php?id=...&t=$(date +%s)" | python3 -m json.tool
```

Cache-busting `t=<unix>` params in the HAR are usually required — the CDN caches per-URL.

## 4. Watch for header-gated endpoints (the trap)

A URL that returns **404 on a plain GET is not necessarily dead**. It may be gated on a
custom header whose value comes from an earlier response.

Real example: `video.php` returned `{hls_key: "...", file: "[<font>480p</font>]https://host/e/<token>,..."}`.
Fetching `https://host/e/<token>` → 404. Fetching the *same URL* with
`X-Hls-Key: <hls_key>` → the real `#EXTM3U` playlist. Before declaring an endpoint broken,
re-send it with every non-standard header/JSON field that appeared alongside it.

## 5. Expect content disguised as other file types

The HLS segments in that playlist were `/fonts/<id>/font-000.woff` with
`#EXT-X-MAP:URI=".../font.ttf"` — video chunks named as fonts to slip past filters.
Segment paths that look wrong for their content type are normal; resolve them relative to
the embed host and verify one with `HEAD`.

## 6. Chain discovery, then stop

Write down the minimal chain and verify it end to end before coding:
`detail page → id in an onclick/inline JS → list endpoint → item endpoint → stream URL`.
Verify with real curl output at each hop, then port it to code.

## Consumer-side caveat

An endpoint that needs a custom header per request also needs a player/client that can
send headers **per segment**, not just on the manifest. If the client can't, plan a small
server-side proxy that injects the header and rewrites segment URLs — decide this before
promising "direct streaming works".
