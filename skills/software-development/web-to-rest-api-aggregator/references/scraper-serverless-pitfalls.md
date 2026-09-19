# Scraper & serverless debugging pitfalls (Xyra API, Aug 2026)

Each entry is a real bug that cost debugging time. Add these to your mental checklist before blaming the source site.

## 1. Chapter pages are mixed-content — filter by requested path segment

A provider's "chapter N" page can embed preview/recommendation images from 5+ other chapters (e.g. folder `900, 899, 898, 897, 896` alongside the requested `681`). A naive `matchAll` on image URLs returns every folder — output looks like the wrong chapter, and page counts are inflated.

Diagnosis: grep the fetched HTML for all folder segments (`/Title/(\d+)/`) and count how many folders appear. Fix:

```js
const pat = new RegExp(`/${chapter}/`);
return [...new Set(imgs.filter(u => pat.test(u)))];
```

Verification trap: the same chapter may legitimately have duplicate URLs in the HTML (RSC renders the list twice) — dedup with `Set`, don't panic when raw count = 3× unique count.

## 2. URL format drift across content age

New content and old content often live on different URL patterns. Komiku example: new chapters `image5.komiku.to/upload5/bleach/687.2/2026-07-10/1.jpg`, old chapters `image10.komiku.to/wp-content/uploads/2271541-1.jpg`. A regex tuned on fresh content (`image\d?` + `/upload`) silently returns 0 for every old chapter → "chapter tidak ditemukan".

Fix: multi-digit host + alternation — `image\d+\.komiku\.to\/(?:upload|wp-content\/uploads)[^"\s]+?\.(?:jpg|webp|png)`. Also strip promo/placeholder images that don't match the chapter path at all.

## 3. cached() returns a wrapper — ALWAYS destructure { data }

If your cache helper is `cached(key, ttl, fn) => ({ data, ts })`, then:

```js
// WRONG — images becomes the wrapper object; images.length is undefined → silent 404
images = await cached(key, ttl, () => scraper.scrapeChapter(slug, num));
// RIGHT
const { data } = await cached(key, ttl, () => scraper.scrapeChapter(slug, num));
images = data;
```

This bug is invisible: the route exists, the scraper works, the URL is valid — only the `.length` check fails. It also burns a long debug session because the same cache key works fine in the sibling endpoint that destructures properly. Grep all `= await cached(` for missing destructuring when one endpoint 404s while its twin works.

## 4. Serverless mirror discipline (Vercel api/index.js)

Every route added to `server.js` must be copied to `api/index.js`. Three separate 404s this session came from forgetting: `shinigami/genres`, a player-images route, and a hardcoded health value (`ok:null` vs `ok:true`). After adding any route to server.js: (1) `grep -c` it in api/index.js before deploying, (2) curl it on the fresh deployment URL after deploy.

## 5. Docs "Try this request" sample tables must key on placeholder paths

Interactive docs that build request URLs from endpoint definitions (`ep.path` with `:source/:slug/:num`) will silently send literal `:source` if the sample lookup table uses concrete keys (`/api/global/chapter/komiku/bleach/687-2`) that never match the placeholder path. Result: users see "source harus komiku / voratoon" errors from the docs page itself.

Fix: key the samples map by the placeholder path exactly, with values as a placeholder→value object, and replace in a loop:

```js
const SAMPLES = {
  '/api/global/chapter/:source/:slug/:num': { ':source': 'komiku', ':slug': 'bleach', ':num': '687-2' },
};
// on click:
for (const [ph, val] of Object.entries(sample)) url = url.replace(ph, encodeURIComponent(val));
```

## 6. vercel.json: `functions` conflicts with `builds`

You cannot set `"functions": { "api/index.js": { "maxDuration": 60 } }` when also using `"builds"` (needed for `includeFiles: scraper/**`). Vercel rejects the deploy: "The `functions` property cannot be used in conjunction with the `builds` property." Keep `builds`; accept the default function timeout, and design heavy scrapes to be resilient (see below).

## 7. Vercel 10s function timeout vs heavy scrapes

Next.js RSC pages (400KB+ HTML) scraped from a Vercel edge region can exceed the default 10s function timeout intermittently — the same scraper works from Termux/Indonesia in ~1s. Wrap per-source fetches in `Promise.allSettled` so one timed-out source doesn't take down the whole aggregated endpoint; the response just lacks that source. Warm the slow source's cache with a direct call to its own endpoint first if you need it in the aggregate. Don't burn time on `maxDuration` — it's incompatible with `builds`.
