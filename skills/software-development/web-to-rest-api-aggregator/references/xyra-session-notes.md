# Session learnings — Xyra API (3-source comic aggregator), Aug 2026

Session-specific detail backing web-to-rest-api-aggregator SKILL.md. Real bugs and fixes from building/shipping a 3-source comic REST API (voratoon RSC + komiku HTML + shinigami official API) on Express/PM2 local + Vercel serverless.

## Serverless/local parity failures (hit 3x in one session)

Routes added to `server.js` but not `api/index.js` → live 404 on Vercel while localhost works. Affected: `/api/shinigami/latest`, all `/api/global/*`, `/api/player/:source/:slug/chapter/:num`. Checklist after any route change:

```bash
grep 'route/path' server.js api/index.js   # must appear in BOTH
node --check server.js && node --check api/index.js
pm2 restart voratoon-api && vercel deploy --prod --yes --token ...
curl -sw '%{http_code}' https://<alias>/api/<new-route>   # verify LIVE, not local
```

Also bit once: CORS middleware pasted into `api/index.js` using `app.use` when the express instance is named `api` — compiles fine, 500s (`FUNCTION_INVOCATION_FAILED`) only on Vercel.

## Mixed-identifier source (UUID vs slug)

Shinigami uses UUID mangaId + separate chapterId; Komiku/VoraToon use slug + numeric chapter. Forcing Shinigami into unified `/api/global/chapters/:source/:slug` produced constant "source tidak valid" errors visible in the docs-page demo buttons. Resolution: global chapters/images = komiku+voratoon only; Shinigami keeps its own endpoint family and participates in aggregations via per-provider storage. Lesson: unified endpoints need uniform identifier schemes; error messages should enumerate valid sources.

## Player endpoint pattern

`GET /api/player/:source/:slug?chapter=NUM` → detail + full chapter list + nav meta (firstChapter/lastChapter/newestChapter) + 20-chapter preview (+ optional images). Sibling `GET .../chapter/:num` returns images only for reader paging. Bug hit: Shinigami's detail payload has no chapters array — chapters come from a paginated call; destructuring `cj.chapters.map()` on the cached wrapper result (which is `{data, ts}`) threw `Cannot read properties of undefined`. Destructure `.data` off cache wrappers.

## Mobile frontend tap handling

Registering both `touchend` and `click` handlers double-fires on Android browsers: one tap toggles the card open then instantly closed; user perceives needing "3 lucky taps". Fix: single `pointerup` handler with `closest('.code-block,.trybtn,.result')` guard, plus CSS `touch-action:manipulation`, `-webkit-tap-highlight-color:transparent`, ≥48px tap targets.

## Docs "try request" buttons

Without a SAMPLES map keyed by parametric path (`'/api/player/komiku/bleach/chapter/687-2': ['bleach','687-2']`), demo clicks fetch literal `:source/:slug` paths and display your own validation errors to users. Fetch real IDs dynamically where needed (e.g., pull first Shinigami UUID from list endpoint, then its chapterId).

## Chapter-list UX (Lumen-style, user-preferred)

Full-width rows: `Chapter N ......... [BARU] 2 hari lalu`. BARU badge for newest 1–2 chapters aged ≤7 days. Verbose relative times everywhere ("18 menit lalu", not "18m"). Per-chapter timestamps estimated by stepping backwards evenly from latestChapterAt when providers don't expose per-chapter dates.

## Vercel alias drift

After many deploys, short alias returned `DEPLOYMENT_NOT_FOUND` while direct deployment URLs worked fine. `vercel inspect <deployment>` showed aliases had moved to a new domain (`xyra-api.vercel.app`). Don't fight the old alias — re-point docs/users to current alias.

## CORS

Missing `Access-Control-Allow-Origin` = browser clients blocked ("kena begal CORS"). Open API → `*`. Preflight OPTIONS must bypass the rate limiter or preflights get counted/blocked.
