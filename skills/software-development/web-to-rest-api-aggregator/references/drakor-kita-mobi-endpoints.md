# drakor.kita.mobi — Endpoint Map & Analysis (Aug 2026)

Discovered via HAR capture (mobile devtools, 68 entries) + Node VM deobfuscation of `a.js`.

## Base

| Item | Value |
|------|-------|
| Site | https://drakor.kita.mobi |
| API Host | `https://api.nonton.bid/c_api/` |
| Search | `GET /all?q={query}` (form action, method=get) |
| Catalog | `GET /all?page=N` (296 pages) |
| Genre | `GET /all?genre=X` |
| Status | `GET /all?status=ended\|returning series` |
| DRM | None — public site, no login required |

## Endpoint API (api.nonton.bid/c_api/)

All reachable *without* anti-leech params (`t`, `ver`, `c` are optional — tested clean).

### episode.php — daftar episode
```
GET /c_api/episode.php?is_mob=1&movie_id=<FIRST_EP_ID>
```
- `movie_id` = episode ID pertama dari halaman detail (dari `loadEpisode('ID',...)`)
- Returns: `{ptype, server_xid, first_ep_id, episode_lists: "<a>...</a>"}`
- `episode_lists`: HTML dengan `<a data-epid="EPID" class="epz-N">N</a>` per episode

### server_mob.php — pilih server/kualitas
```
GET /c_api/server_mob.php?is_mob=1&episode_id=<EPID>&cat=hs&tag=ind&server_xid=f1
```
- Returns: `{data: {server_xid, ptype, svname, episode, ...}, server_lists: "<HTML buttons>"}`
- `server_xid` = `f1` (default server)

### video.php — stream file
```
GET /c_api/video.php?is_mob=1&id=<EPID>&qua=web&server_id=f1&cat=hs&tag=ind
```
- Returns: `{hls, hls_key, file, next, prev, cuid, title, poster, ...}`
- `file`: HTML format `[<font i="FILE_ID" ...>480p</font>...]https://seniman1.uyeshare.cc/e/...,[...720p...]...`
- `next`/`prev`: episode ID untuk navigasi episode
- Cloudflare-cached max-age=31536000 (1 tahun) — tapi embed URL expired dalam menit

### video_p2p.php — P2P alternatif
```
GET /c_api/video_p2p.php?is_mob=1&id=<EPID>&qua=web&res=480&server_id=f1&cat=hs&tag=ind
```
- Returns: `{p2p_status:1, p2p_url: "https://drakorkita.stream/#..."}`

### video_hydrax.php — Hydrax alternatif
```
GET /c_api/video_hydrax.php?is_mob=1&id=<EPID>&qua=web&res=480&server_id=f1&cat=hs&tag=ind
```
- Returns: `{hydrax_status:1, hydrax_url: "https://abysscdn.com/?v=..."}`

## CDN Chain

```
video.php → embed (seniman1.uyeshare.cc/e/...) → CDN (1xmaza.drakor.bid/galeri/...)
```

CDN path pattern:
```
https://1xmaza.drakor.bid/galeri/<mid[0:2]>/<mid[2:4]>/<file_id>/init.mp4
https://1xmaza.drakor.bid/galeri/<mid[0:2]>/<mid[2:4]>/<file_id>/out000.m4s
...
```
- `mid` = movie_id (first episode ID, e.g. `0Nq3d8gCQC` → `0N`/`q3`)
- `file_id` = dari `<font i="...">` di `file` field video.php (e.g. `x2lEJIzD0MyUSN`)
- DASH segments tanpa manifest (.mpd/.m3u8)
- CDN serve `video/mp4` content-type, accept-ranges bytes

## Halaman Detail (selector)

| Field | Selector |
|-------|----------|
| ID | Extract from `loadEpisode('ID','hs','ind')` in HTML |
| Title | `h1[itemprop="headline"]` (clean: strip "Nonton ... Subtitle Indonesia") |
| Alt Title | `.alter` |
| Poster | `img.poster` (tmdb) |
| Genre | `.gnr a` → `/all?genre=X` |
| Synopsis | `.sinopsis .desc-wrap p` |
| Rating | `.rating .rtg` (stars) |
| Episode list | `episode.php?movie_id=<FIRST_EP_ID>` |

## Halaman Homepage

- Grid kartu `a.poster` → `/detail/{slug}/`
- `img.poster` → `src` (tmdb), `alt` (judul)
- `span.titit` → judul teks
- `span.type` → durasi / `E4/12` (ongoing episode count)
- Section headings: tidak ada heading eksplisit — semua konten satu grid

## Obfuscated JS

- `a.js?v=...` (74KB) — custom obfuscator: string-array + hex-index + per-index key
  (`_0x5451(idx,key)`); IIFE shuffle array on load
- `player/mobl.js` (703KB) — player library (murni, tidak ada endpoint)
- `player/desl.js` (683KB) — DASH player library
- Fungsi terekspos dari `a.js` via VM: `loadEpisode`, `initEpisodeList`, `loadServer`,
  `loadVideoLoc`, `loadVideoHYDRAX`, `loadVideoP2P`, `loadVideoSB`, `get_link`, `getUrlParams`
- `get_link` — kemungkinan transform URL embed → URL final (belum diverifikasi)
- `c_api_host` didapat dari HAR, bukan dari HTML/JS

## Pitfalls & Gotchas

- **Embed URL expires ~10 menit** — `video.php` return URL seniman1 yang sama, tapi
  embed page 404 setelah beberapa menit. CDN segments tetap hidup lebih lama.
- **`t`/`ver`/`c` params tidak wajib** — tes dengan menghilangkannya: semua 200 OK.
- **`video.php` di-cache Cloudflare 1 tahun** — fresh API call ≠ URL embed valid.
- **`episode.php` butuh `movie_id` spesifik** — parameter `slug` tidak bekerja.
  `movie_id` = episode ID pertama dari halaman detail.
- **HAR response body 0 chars** — replay dengan curl pake URL + headers yang sama.
- **`/tmp` read-only di Termux** — tulis probe ke `~`.