# NOVA Home design spec (extension-hub-pro)

User-approved Home layout, decided 2026-08. Apply this when redesigning Home —
do NOT fall back to a generic "katalog" (10-15 sections) layout; user explicitly
rejected that ("mau Home-nya tetap clean, aku justru nggak menyarankan 10–15 section").

## Section order (fixed)
```
HOME
├── Update Terbaru           → horizontal carousel (keeps existing)
├── Lanjutkan Menonton       → conditional, only if watch history exists
├── Drama Populer 🔥
├── Drama Ongoing
├── Baru Ditambahkan ✨
├── Sudah Tamat ✓
├── Rekomendasi Untukmu
└── Genre                    → chips row
```

## Card hierarchy (poster title must NOT cover the poster)
```
┌──────────────┐
│              │
│    POSTER    │   play overlay on hover, rating/quality/premium badges
│              │
└──────────────┘
│  Title (2 lines)      │   <-- below poster, .poster-body
│  ● src   EP 12        │   <-- metadata: source + status + year
└───────────────────────┘
```

## Implementation notes (verified working)
- Section source per Home section: pick ONE source via priority list
  (`drakorid → drakorkita → anichin → otakudesu`) rather than fanning out all
  sources — avoids the 25-worker OOM cascade (see SKILL.md "Cascade kill").
- Home sections render as grid (2-3 cols), ONLY "Update Terbaru" is a carousel —
  gives visual rhythm, avoids monotony.
- Continue Watching: localStorage key `eh-watch-history` (max 50). Written on
  `openDetail` via `window.__saveWatchHistory` (home.js) called from detail.js —
  do NOT wrap `openDetail` in home.js directly: home.js loads BEFORE detail.js in
  `index.html`, so the wrap captures `undefined`. Use a deferred helper.
- State-enabled gotcha: sections API returning "source tidak mendukung sections"
  usually = extension disabled in `.data/state.json`, not missing capability.
- Verify sections per source: `curl localhost:3001/api/sections?source=<id>`
  (otakudesu: ongoing/completed/schedule/genres; anichin: +popular/movie/recommendation;
  drakorid: +popular/terbaru/favorit/catalog; drakorkita: terbaru/ongoing/catalog/completed/movie/genres).
- New field on extension output (e.g. `premium`) must be added to the
  `normalizeEpisode`/`normalizeDetail` pass-through in `sdk/models.js` or it
  silently vanishes from the API.
