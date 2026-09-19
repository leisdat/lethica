---
name: extension-plugin-systems
description: Use when building multi-source extension/plugin in Node.js.
---

# Building extension/plugin systems (multi-source, Node.js)

Architecture for apps where third-party "extensions/sources" plug into a host app
(media sources, scrapers, connectors). Verified end-to-end on Extension Hub Pro:
extension manager, signed repository, SHA-256 integrity, permission policy, worker
isolation, real HTTP scraper extension, mobile-first UI — 79/79 tests.

## When to use
- App that aggregates multiple sources/extensions with a common contract
- Need install/uninstall/enable/disable/update lifecycle
- Need to run untrusted extension code without killing the host
- Need repository updates without app updates

## Architecture (layered, keep it strict)
```
UI → Unified Source API (normalize + dedup + sourceId)
      → Runtime (per-call timeout, try/catch, capability check)
          → Extensions (manifest.json + index.js contract)
Extension Manager (state: installed/enabled/version → storage.json)
Repository (manifest repo, refreshable, signed)
```
Separation rules: no hardcoding sources in UI, no per-source UI, no business
logic in scrapers, no inter-extension deps, one extension failing must never
stop others, never assume a source is always available.

## Contract-first SDK
Extension exposes exactly: `search(query)`, `getDetail(id)`, `getEpisodes(id)`,
`getEpisodeSources(episodeId)` — plus optional capabilities (`latest`, `trending`,
`genres`, `byGenre`) for home/aggregator feeds.

**Pitfall — capability validation rejects new capabilities:** `validateCapabilities`
that only knows REQUIRED_FUNCTIONS will refuse valid extensions declaring `latest`/
`trending` ("capability X tidak dikenal"). Maintain TWO lists: REQUIRED_FUNCTIONS
(contract, must exist) and OPTIONAL_FUNCTIONS (allowed extra, must exist IF
declared). Both checked at install; only REQUIRED enforced.

**Pitfall — normalizers silently drop extension data:** `normalizeDetail` returning
a fixed whitelist (id/title/desc/genres/status/thumbnail) throws away extension-
provided extras (rating, type, duration, totalEpisodes) → API shows `null` even
though the worker returns the data. Normalizers must pass through optional fields
when present: build the base object, then `for (const k of extras) if (raw[k] != null) out[k] = raw[k]`.

## Runtime isolation (worker_threads, no deps)
- Run every extension call in `worker_threads` (NOT main process). Message protocol:
  request `{id, method, args}` → response `{id, ok:true, result}` | `{id, ok:false, error:{code,message}}`.
- Timeout = terminate the worker, don't just reject the Promise (`worker.terminate()`).
- `worker.unref()` alone does NOT let the process exit cleanly (Node 24) — add an
  idle-timeout auto-terminate (e.g. 2s after last request) so test processes end.
- Worker pool keyed by extension id; restart worker after crash/timeout.
- Extensions require modules via relative path from their own dir; worker script
  requires by absolute path (relative fails). Multi-file extensions work: the
  sandbox allows `require()` inside the extension's own folder — proven layout:
  thin `index.js` (docs + re-exports) + `lib/{http,cache,parse,catalog,detail}.js`;
  hot-reload covers the lib files too.
- **Cascade kill (bulk `worker keluar code 1`):** all requests to one extension
  queue in the SAME worker (pool keyed by extension id). One request hitting its
  per-call timeout → `terminate()` → every queued request dies at once with
  `WORKER_EXIT code 1` and NO crash trace. Trigger: a home screen fanning out
  ~10 parallel API calls (catalog 6 upstream pages + latest 12 pages + detail…)
  while heavy methods sit in front of the queue. Fix: propagate `limit`
  end-to-end — UI carousels ask ~24, "view all" asks full, core passes the
  limit INTO the extension method args (`section(id, limit)`) so heavy sections
  stop early — and raise per-call timeout for expensive capabilities (60s).
  Debug signature: mass WORKER_EXIT without stack traces = the queue, not the site.
- **Limit propagation is a CONTRACT — the extension must HONOR it:** core passing
  `limit` into `section(id, limit)` is only half the fix. Real extensions shipped
  with `section(id)` (no second param) hardcoded to ONE page (24/20 items) — the
  limit arrived and was silently ignored, so "view all" showed a sliver of the
  catalog while every test passed. Pattern: `section(id, limit = 0)`, multi-page
  `scrapePages(baseUrl, limit)` loop (dedupe ids across pages, stop on
  empty page / fetch error / limit reached, maxPages = `ceil(limit/PAGE)+2`).
  **Measure the site BEFORE writing pagination** (items/page + depth):
  `curl -s <list-url> -o ~/pg.html && grep -c '<card-class>' ~/pg.html` and
  `grep -oE 'page/[0-9]+/' ~/pg.html | sort -u`. Verify end-to-end with
  `limit=200` and count items in the response — assert count > single-page size.
  Full proven `scrapePages` (2 selector variants) + verification commands:
  `references/scrape-pagination.md`.
- **Query-string pagination quirk:** list URLs WITH a query string
  (`/seri/?status=&type=&order=popular`) often paginate to
  `/seri/page/2/` WITHOUT the query — repeating the query (`/seri/page/2/?status=...`)
  can return a **0-byte 200 response** (not 404!). A 0-byte page in a pagination
  loop means "wrong URL format", not "no more pages" — test both formats with
  curl before coding the page-2 URL builder.

## Repository + trust model
- Remote repo: HTTPS-only (config `allowInsecure` for localhost tests), timeout,
  status validation, JSON + schema validation, descriptive errors. Fallback chain:
  REMOTE → CACHE (last valid) → BUNDLED. Never cache an invalid repo.
- Canonical JSON for signing: sorted object keys, array order preserved, UTF-8,
  no whitespace. Sign `{schemaVersion, repository, extensions}` — NOT the
  signature field itself.
- Ed25519 via Node crypto (never roll your own). Keyring: `active` (verify),
  `deprecated` (verify + warn), `revoked` (reject). App holds trusted keys; repo
  only sends keyId. Unknown key → reject.
- SHA-256 integrity on package download: download → hash → compare → install.
  Mismatch → reject, keep old version. Hash = integrity, NOT trust.
- Atomic install: download → verify → prepare temp dir → validate → activate →
  remove old. Old version survives any failure. `allowDowngrade = false` default.
- Permissions: manifest declares, policy approves. No wildcard ("*"/"all").
  `shell` → NEVER. Structured error `PERMISSION_DENIED {extensionId, permission}`.
- HONESTY: report `implemented / partially / mock / not implemented`; document
  limitations clearly. Do not claim security that isn't there.

## Multi-source aggregation
`Promise.allSettled` over enabled extensions; normalize per-source; dedupe by
normalized title key; keep `sourceId` on every result. `latest()` should prefer a
dedicated extension method (`latest`) with `search("")` fallback.

## Testing pitfalls (multi-file suites)
- `node --test <dir>` can fail on some paths (Termux) — run files explicitly or
  use a sequential `run-all.js` that spawns each test file in its own process.
- Suite reported as `tests 1, fail 1` = file crashed in `before()`/top-level —
  read raw output ABOVE the summary (EADDRINUSE, `Assignment to constant variable`).
- Mock servers: `listen(0)` + read `server.address().port`; set consumer env
  AFTER port known (in `before()`, not module load). `let` not `const` for the port.
- `rm -rf .data*` before suites — a running server's state bleeds into tests.
- Real-site scraper tests: wrap in soft-fail (skip if site unreachable) so the
  suite doesn't depend on external uptime.
- **jsdom smoke harness for split vanilla-JS UIs:** `window.eval()` per file
  does NOT share top-level `const/let` between eval calls (browser `<script>`
  tags DO share the global lexical env). Concatenate all module files into ONE
  string and eval once — semantically equivalent to the real load order.
- **`async` function called without `await` → Promise used as array:**
  a vanilla-JS view file defines `window.openWatch = function(media) { watchPlaylist = buildWatchPlaylist(media); ... }` where `buildWatchPlaylist` returns a `Promise`. The code then calls `watchPlaylist.findIndex(...)` — the Promise doesn't have `.findIndex`, producing `TypeError: watchPlaylist.findIndex is not a function`. The fix: `async function` + `await` on the call. This is easy to miss because `node --check` passes (the syntax is valid), no static analysis catches it, and the error only surfaces at runtime when the user clicks "Play". The pattern to watch for: any function that you KNOW is `async` (or that calls `await` internally) must be called with `await` from its caller, and the caller must be `async` too. This cascades upward through the call chain.
- **After a refactor, live-test the HEAVY path, not a sibling:** this session's
  modularization broke only the catalog section (missing `BASE` import in a new
  lib file) while favorit/ongoing worked — unit tests (mock extensions) and a
  light-section spot-check both passed. Smoke against every capability the
  refactor touched, heaviest first.
- **Worker timeout must cover the extension's real worst-case path.** Default
  per-call timeout (e.g. 10s) silently kills multi-step methods (warm-up fetch +
  watch-page fetch + retry). `ok:true` with empty data can BE the timeout
  manifesting as truncated work — raise per-call timeout for the expensive
  capability (`runIsolated(..., 40000)`) and skip optional second passes (e.g.
  don't fetch `watch-max` if `watch-lite` already yielded streams).
- **Extension file edits hot-reload (worker rebuilt per call); host-module edits
  (sources/server) need a FULL server restart.** After patching host code, kill
  the node process by PID (`kill -9` — the old background session may already be
  dead while its ghost child still holds the port, then a new session dies with
  EADDRINUSE), restart, and only then run the audit.
- **Audit scripts vs burst throttling:** an audit that walks many endpoints hits
  upstream sites ~20x in a row and trips throttles a normal user never sees —
  the audit then FAILS on exactly the capability it's proving broken. Order the
  audit to exercise the throttle-prone capability FIRST, add one spaced retry
  (8s), and cache detail HTML (~60s, LRU ≤50) so one user flow = one upstream
  fetch.
- Scraper audit = assert NON-EMPTY output per capability, not just ok:true.
  `ok:true` + 0 items means silent selector rot (site layout drifted) — treat as
  failure. See references/media-scraper-patterns.md pitfall #7 for the
  fetch-live-page → read-real-markup → fix-selector → re-verify workflow.
  Per-site profiles: references/otakudesu-scraper.md, references/drakorid-scraper.md
  (drakorid: hidden AJAX catalog, HD poster via size-in-URL proxy, warm-up gate,
  burst throttle, upstream link-rot vs scraper bugs, guest-limit 1x/day, PREMIUM
  episodes). NOVA Home design spec (fixed section order, card hierarchy, clean
  Home): references/nova-home-design.md.

## User expectations (Indonesian dev, Termux)
- Honest status reports: implemented vs mock vs not — never claim a feature works
  because a UI button exists.
- No bypass-DRM / auth-bypass / paid-content theft: refuse modded Netflix APK
  etc., offer legal alternatives (public APIs, RSS, public-domain).
- "Masih error audit lagi" (recurring complaint) usually means: server process
  died (port held by killed background process) OR inline-script syntax error
  made the whole UI inert OR **stale browser cache**. Check server liveness +
  `node --check` the extracted script BEFORE deep-diving features, and verify
  the served bytes match disk (`curl --compressed | wc -c` vs `wc -c < file`).
- **Stale browser cache masquerading as a code bug:** serving JS/CSS with
  `Cache-Control: public, max-age=3600` makes a phone browser keep a broken
  build for up to an hour — user keeps reporting the SAME SyntaxError after
  every fix, files on disk are fine, `node --check` passes. The fix is the
  HEADER, not the code: in dev serve `no-cache` for ALL text assets (browser
  revalidates each request; edits apply on a normal refresh, no hard-refresh
  needed). Always diff served-vs-disk size to rule cache/truncation out.
- **Misleading capability error = disabled extension:** `sections`/`section`
  API returning "source tidak mendukung sections" while the manifest clearly
  declares the capability usually means the extension is DISABLED in
  `.data/state.json` (`enabledExtensions()` filters on state, not on the
  manifest). Check `enabled` before trusting the error text — and remember
  editing state.json requires a full server restart (state is cached in
  memory).