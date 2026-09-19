# Drakorid scraper profile (extension-hub-pro, v1.3.0)

Reference for maintaining `extensions/drakorid/` (BASE: `https://drakorid.co`).
Modular since v1.3.0: thin `index.js` re-exports `lib/{http,cache,parse,catalog,detail}.js`
(sandbox-verified local requires). Most complex source in the hub: hidden AJAX
catalog, full catalog at `/list/N`, image proxy, warm-up gate, burst throttle.
Audit script: `scripts/audit_drakorid_v11.py` in the repo.

## Endpoint inventory (verified 2026-08)

| Capability | How |
|---|---|
| search | `GET /cari.html?q={q}&p={page}` — grid `article.movie-list-card`; page 2 exists even without visible pager; ~7 items/page |
| latest | `POST /ajax/index_terbaru.php` — **fixed 15 items, NO pagination** (probed `page`/`paged`/`halaman` params — all ignored, byte-identical 10264B response). For limit>15 continue with `/list/N` |
| **catalog** | `GET /list/{n}` — **the real full catalog**: ~33 items/page, urut terbaru, 2600+ titles (probed to page 80+). ~5 items per page are a sticky "Sedang Tayang" block (dedupe) |
| trending | AJAX `index_trending.php` + `index_favorit.php` (~25) PLUS `GET /trending.html` (44-item rail, **`article.trending-card` markup — different from movie-list-card!**) → 54 merged |
| completed | **No such page on the site** (drama-completed/tamat/etc all 404) — built from TAIL pages of `/list/` (p80-82, old entries ≈ tamat) + per-title status heuristics |
| ongoing | `POST /ajax/index_ongoing.php` (~15), fallback `GET /drama-ongoing/` (only ~5 items — mostly empty) |
| detail/episodes | `GET /nonton/{slug}/` — episodes from `[data-episode]` buttons; rich metadata as `Label: Nilai` text rows (Genre/Director/Network/Duration/Country/Episode) → typed fields; status heuristic: released ep buttons < total → Ongoing, year < current → Completed |
| sources | `GET /watch-{lite,max}/{slug}/{N}` with `Referer: {BASE}/nonton/{slug}/` — iframe `player/bunny.php?v=<base64 m3u8>` per quality (360/480/720) |

All AJAX: POST body `token=<token_now>`, headers `X-Requested-With:
XMLHttpRequest` + `Referer: {BASE}/`. Token = inline `var token_now = "..."`
in the homepage HTML; cache ~10 min, re-fetch homepage once on `"Token Not
Found"` body. AJAX cards link to `/go/{id}` (302 → `/nonton/{slug}/`) —
resolve via `redirect: "follow"` + read `res.url`.

## The 4 gotchas (each was a real bug)

1. **Poster HD:** images served via proxy with size in URL:
   `convert.d-cdn.me/convert/<base64url>/72x72/1.jpg`. Rewrite any
   `/NNxNN/` segment → `/480x640/` (`hdThumb()`). Proxy accepts arbitrary
   sizes; 72x72 ≈ 3KB vs 480x640 ≈ 62KB.
2. **Warm-up gate:** watch page returns 200 but iframe-less unless the detail
   page was fetched first. `getEpisodeSources` must `cachedDetail(slug)` before
   the watch fetch, retry once if body lacks `bunny|player`.
3. **Burst throttle:** ~a dozen rapid upstream hits → minutes-long throttle
   serving player-less pages. Seconds-scale retries don't clear it; single
   request after ~3 min works. Countermeasure: 60s LRU detail cache (≤50
   entries) + audits test sources FIRST.
4. **Worker timeout:** full sources path (resolve + warm-up + watch + retry)
   exceeds the host's 10s default → host calls `runIsolated(..., 60000)` for
   section/latest now; skip `watch-max` when lite already yielded streams.
5. **Cascade kill via shared worker queue:** Home fans out ~10 parallel calls
   (catalog=composites of 6 upstream pages, latest=12 pages, detail…) — all
   queue in the ONE worker per extension; a timeout kills the worker and every
   queued request errors `worker keluar (code 1)` at once (no stack trace).
   Countermeasure: `limit` propagated into `section(id, limit)` (carousel asks
   24 → catalog stops at page 1 instead of 6) — see SKILL.md "Cascade kill".

## Known upstream limits (NOT scraper bugs — don't "fix" these)

- Brand-new series (e.g. anything currently-airing 2026) often has NO player on
  the site yet → sources legitimately empty for the newest items.
- Last episodes of older series frequently link-rot (legacy host `drakor.id`
  is dead) → verify with curl full-flow before blaming selectors.
- `/kategori.html` genre listing still works (63 categories,
  `/kategori/{slug}/{page}`).
- **Guest limit 1x/day (2026-08):** watch pages for guests return 200 with a
  login message ("...hanya bisa streaming 1x dalam sehari, silahkan login")
  INSTEAD of the player iframe — so sources come back EMPTY even for free,
  non-premium episodes once the cap is hit. Not a selector bug. This also
  means: don't chase "sources kosong" as a code bug without first checking the
  watch-page body for this message.
- **PREMIUM ONLY episodes:** episode buttons labelled "PREMIUM ONLY!" have no
  player regardless of guest state. Detect + flag them (`premium: true`) in
  `getEpisodes` so the UI can show a lock badge instead of a play button that
  fails. IMPORTANT: the `normalizeEpisode` whitelist in `sdk/models.js` drops
  unknown fields — the `premium` flag silently vanished from API responses
  until the normalizer was changed to pass through `raw.premium`. When adding a
  new field to extension output, always check the normalizer pass-through.
- **Detection pattern:** in `getEpisodeSources`, scan the watch-page body for
  the guest-limit phrase; if found (and no streams), throw a structured error
  (`GUEST_LIMIT: ...`) instead of returning `[]` — the UI shows a clear
  "login needed" message rather than a confusing empty server list. Do NOT
  bypass the guest limit (auth bypass) — user policy.

## Quick verify (node, hits live site)

```bash
node -e "const d=require('./extensions/drakorid/index.js');d.latest(15).then(r=>console.log('latest',r.length)).catch(e=>console.error(e.message))"
node -e "const d=require('./extensions/drakorid/index.js');d.getEpisodeSources('the-time-hotel-2023-ep-1').then(s=>console.log('sources',s.length)).catch(e=>console.error(e.message))"
```

Full E2E via API: `python3 scripts/audit_drakorid_v11.py` (server must be
restarted after host-module changes; ordering: sources test first).
