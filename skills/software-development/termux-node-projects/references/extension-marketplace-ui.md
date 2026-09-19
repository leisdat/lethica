# Extension Manager Marketplace UI (user spec, letticha) + Health Check pattern

User reviewed a reference marketplace screenshot and specified exactly how an
extension-manager UI should behave. Implemented in `~/extension-hub-pro/app/ui/index.html`
+ `core/health.js` + `/api/extensions/health`. Verified live.

## Core concept: Repository ≠ Installed (the UI must make this visible)

- Repo holds N extensions (e.g. 39); user installs only some (e.g. 3).
- Card must show state: `Install` (in repo, not installed) vs `Uninstall`
  (installed). Uninstall removes the LOCAL install only — the repo still lists it.
- Runtime only runs extensions that are **Installed AND Enabled** (toggle on card).

## Repo header & categories (never hardcode counts)

- Header: "Extensions" + subtitle "N extension tersedia di repository".
- Stat cards: Total / Terpasang / Aktif (computed, not hardcoded).
- Category chips with counts derived from `manifest.category`:
  `Anime (12) · Movie (3) · Short Drama (22)`. Backend aggregates:
  `/api/state` returns `categories: {anime: {total, installed}, ...}`.
  New category tomorrow → UI shows it automatically.

## Extension card (one card, all state)

```
[icon]  Name                    [toggle on/off]
        author · v1.0.0
ANIME  ✓Terpasang  🟢Aktif  ●Live  [v1.1.0 update badge]
[Install / Uninstall]
```
- icon: gradient box + first letter (or emoji pool keyed by id length).
- tags: category, Terpasang, Aktif/Nonaktif, health status, update badge
  (shown when `installedVersion !== manifest.version`).
- whole card clickable → detail modal; action buttons stopPropagation.

## Detail modal (card click)

Icon, name, version, Author, Category, Status (● Live), Capabilities
(search/getDetail/getEpisodes/getEpisodeSources), Permissions (Network),
Description, one primary action button (Install ↔ Uninstall).

## Health status per source (NOT "is it enabled")

Semantic: `● Live` = source responds to a quick probe; `Updating`; `Offline` =
timeout/network; `⚠ Error` = extension throws. It is source health, not
enablement. Pattern (`core/health.js`):
- probe = `runIsolated(ext, "search", ["a"], HEALTH_TIMEOUT_MS)` through the
  worker; measure latency.
- WORKER_TIMEOUT → offline; EXTENSION_ERROR → error; ok → live.
- `/api/extensions/health` checks all installed extensions; UI polls every 15s.
- Real scrapers legitimately take ~1-2s (otakudesu 1.7s) — don't use a probe
  timeout shorter than ~6s or everything reads "Offline".

## Install flow (already the contract — keep it visible in UI)

Install button → (permission confirm dialog if manifest declares permissions)
→ metadata → validate manifest → repo signature check → download package →
SHA-256 verify → validate manifest → permission check → install → enable.
UI shows structured error (e.g. "Update rejected: integrity verification
failed") — never raw stacks.

## Design bar (user letticha)

Marketplace UI must be dark/light with manual toggle, glass header, gradient
accents, cards with hover lift — same non-generic bar as the autoblog front-end.

## Home page sections — cache reset bug (fixed, pattern worth keeping)

UI kept per-render caches like `loadedSectionsKey` to avoid re-fetching dynamic
sections. Bug: on refresh/re-entering Home, `renderHome()` rebuilt the DOM but
the stale cache key made `loadDynamicSections()` skip everything → sections
(Rekomendasi/Popular/Ongoing/Completed) vanished, leaving only Update Terbaru +
Semua Konten. Fix: **reset any DOM-adjacent cache at the top of the render
function that rebuilds that DOM** (`loadedSectionsKey = ''` first line of
`renderHome`). Rule: a render fn that wipes innerHTML must invalidate any key
that claims "already rendered" — otherwise cache and DOM disagree silently.

## UI structure refactor (monolith → 3 files, done & verified)

`app/ui/index.html` (1451 lines) split into `index.html` (~100-line shell) +
`css/app.css` (design tokens/components) + `js/app.js` (logic). Pitfalls hit:
- Extracted `<script>`/`<style>` via sed leaves EMPTY leftover tags in index.html
  if you're not careful — remove them.
- A JS syntax error ANYWHERE in app.js kills every button ("gak bisa klik fitur").
  Nested ternaries + arrow functions inside `renderSheet(...)` string concatenation
  broke under one code path. Verify with `node --check` on extracted JS after EVERY
  UI edit, not just before commit.
- Server must serve `/css/app.css` and `/js/app.js` from their real paths; check
  with `curl -s http://localhost:<port>/js/app.js | grep -c <recent-marker>` to be
  sure it's serving the NEW file, not a cached/stale copy.
Modal overlay + blur, mobile-first max-width ~600px.
