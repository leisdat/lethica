# Scraper-as-Extension + Signing Gotchas (Extension Hub Pro, Phase 4)

Phase 4 proved an extension that scrapes a REAL public site works end-to-end through
the whole stack: repo signature → SHA-256 integrity → install → permission(`network`)
→ worker_threads → extension fetch → cheerio parse → normalize → API → UI.
Verified live with `otakudesu.blog` (anime listings, public HTML, no DRM/auth) at
`~/extension-hub-pro/extensions/otakudesu/` — 79/79 tests pass.

## Site-recon-first workflow (do NOT write the extension blind)

1. `curl -sL <url> -H "User-Agent: Mozilla/5.0 (Linux; Android 13)" -o /tmp/page.html`
   — note `/tmp` is unwritable on Termux; use `~/tmp/page.html`.
2. Grep the saved HTML for the real selectors BEFORE coding:
   - otakudesu home listings: `li.detpost` (img + `h2.jdlanime` + link `/anime/{slug}/`)
   - **search results differ from home**: otakudesu search is `/?s={q}&post_type=anime`
     and returns `ul.chivsrc li`, NOT `li.detpost`
   - detail page: `.infozingle` / `.sinopc` / `.episodelist ul li`; episode iframes
     + mirror links
3. Slug = regex from the href (`/anime/{slug}/`, `/nonton/{slug}/`, etc.).
4. Episode numbers from label regex `/Episode\s*(\d+)/i`; sort desc.
5. Non-WordPress sites vary more: drakorid.co is a custom theme — recon found
   ongoing list items with `<a href=".../nonton/{slug}"> title + img`,
   episode buttons carrying `data-episode="N"` attributes, player
   `iframe[src*='player'], iframe[src*='bunny']` whose `?v=` param is base64 of a
   DIRECT HLS/MP4 url (decodable client-side → direct streams instead of iframe!),
   and category pages listing `/kategori/{slug}/{page}` where the human label lives
   in `.in` text minus the count badge. Recon beats assumptions every time.

### Dedup inside stream parsers, not just search results

Drakorid renders the same iframe twice; the naive `.some(s => s.url === src)` dedupe
was O(n²) and rebuilt per call. Use a `Set` scoped to ONE getEpisodeSources call
(`seenUrls`) — never dedupe across calls via module state, or a second episode loses
legit mirrors that happen to share CDN prefixes.

### cheerio text extraction with badges

When a link contains `<div class="in">Name <span class="badge">635</span></div>`,
plain `.text()` gives `"Film Korea   635"`. Strip child nodes first:
```js
$(el).find(".in").clone().children(".badge").remove().end().text().trim()
```
(A trailing-digit regex only masks it; removing the node is robust.)

## Extension contract & normalize

- `npm install cheerio` — pure JS, works fine on Termux.
- fetch with `AbortController` + timeout + mobile UA; throw `Error` on `!res.ok`.
- Extension returns RAW shapes; `core/sources.js` normalizes via `sdk/models.js`
  (SearchResult/Detail/Episode/Stream) — extension code stays thin.
- Multi-source search dedupes by normalized title (lowercase, strip non-alnum);
  same title from scraper + local demo collapses to 1, sourceId preserved.

## Test with soft fallback

Real-site tests must not fail the suite when the site is down:
```js
const res = await w.request("search", ["naruto"]);
if (!res.ok) { console.log("⚠ site unreachable:", res.error?.message); await w.terminate(); return; }
assert.ok(res.result.length >= 1);
```
Use `ExtensionWorker` directly with a 25s timeout, then `terminate()`.

## Repo signing after adding an extension

`node scripts/sign-repo.js` then verify:
```js
const r = require("./repo/extensions.json");
const kr = require("./keys/trusted-keys.json");
r.signature.keyId in kr   // must be true
```

### keyId bug — recompute from private key, never read from keyring
When `private-key.pem` already exists, `sign-repo.js` must recompute keyId from the
public key DERIVED FROM the private key:
```js
const pub = crypto.createPublicKey(priv).export({ type: "spki", format: "pem" }).toString();
const keyId = crypto.createHash("sha256").update(pub).digest("hex").slice(0, 16);
```
Reading `keyId` from trusted-keys.json instead produced `undefined` after re-signing
→ repo signature with an unknown keyId → signature verification fails. Symptom:
`signed keyId: undefined` in sign-repo output, or keyId not in keyring.

## Multi-source demo proof (what "works" looks like)

- install `http-demo` + `otakudesu` → `/api/search?q=...` returns results tagged
  `sourceId: "otakudesu"` — data only exists on the live site, proving the HTTP path.
- 4 sources active (demo-source, demo-source-b, http-demo, otakudesu) → search
  "Hunter" returns demo item + real otakudesu anime, deduped.

## Refuse DRM-bypass "extensions" (policy, not laziness)

A modded/cracked APK (e.g. "N3tflix M0D") is NOT a scraper source — it bypasses
Widevine/DRM and ToS. Refuse, explain why (DRM bypass + malware risk), and offer
legal alternatives: TMDB API, Internet Archive public-domain films, official
trailers via YouTube. This mirrors the repo's own rule: no DRM bypass, no auth
bypass, no paywall evasion, no anti-bot evasion.
