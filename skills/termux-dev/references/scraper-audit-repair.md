# Scraper audit & repair workflow (extension-hub-pro case, verified 2026-08-28)

Proven loop for "optimalisasikan scrape semuanya agar tidak error dan full datanya"
on multi-source hub architectures (extension worker, Express adapter, whatever).
3 real bugs found & fixed in one pass: anichin genres (404 URL), anichin schedule
(empty), drakorid schedule (empty).

## 1. Audit FIRST, per capability — don't trust "search works"
- Enumerate installed sources + declared capabilities from manifests, then probe EVERY
  capability (search with 2-3 queries, latest, trending, sections list, every section id,
  genre:<slug>) with one reusable Python script hitting the REST API. Print ok/len/error
  per row + a failure summary at the end. Save it (e.g. scripts/audit_scrapers.py) —
  it doubles as regression check after every fix.
- Expect false alarms from your own assumptions: probing `section:latest` on sources that
  never declared it returns 400 by design. Compare against the source's own `sections`
  list before calling something a bug.
- Sources may be declared but NOT installed — install them first or you audit half the system.

## 2. Read the REAL error body, not the status code
First audit pass swallowed HTTPError bodies ("HTTP 400") — useless. Catch
`urllib.error.HTTPError` and `json.loads(e.read())`: the real body was
`HTTP 404 untuk https://anichin.cafe/donghua/` which pointed DIRECTLY at the wrong URL.
Error messages from the scraper layer usually contain the exact failing URL.

## 3. Empty result ≠ dead site — repair selectors against live HTML evidence
The empty-section repair loop that worked every time:
1. `curl -sL -A "<real UA>" <page-url> -o ~/page.html` — save the live page locally.
2. Grep the saved HTML for structural markers: class names (`bixbox`, `schedulepage`),
   `data-*` attributes, day/heading text, link prefixes (`/seri/`, `/nonton/`).
3. Rewrite selectors from evidence. Recurring drift patterns:
   - Wrong page entirely: genre list lived on the HOMEPAGE (`/genres/<slug>/` links,
     45 of them), not on a guessable `/donghua/` page. Probe the homepage when a
     dedicated page 404s.
   - Tabs vs panels: `data-dow` existed only on tab BUTTONS; the content panels were
     `data-panel`. Both present in the same widget — count occurrences of each attr
     and inspect the one near actual item links.
   - Locale drift: day names came back in ENGLISH on an Indonesian site → translate
     map EN→ID at scrape time so the API contract stays consistent.
4. While you're in there, harvest free data: schedule items carried release TIME in a
   countdown element (`span.epx`, `data-rlsdt`) — include it (`{id, title, time}`).

## 4. Domain drift — use the BASE actually in the source
Probe with the BASE from the extension's own source code. Typing a sibling TLD
(.xyz vs .co) gives "could not resolve host" which masquerades as "the site died".

## 5. Verify the FULL chain, not just listing endpoints
Passing search/latest/trending says nothing about watchability. Per source, walk
latest → detail(id) → episodes(id) → sources(episodeId) and assert non-empty at each
step, plus one `genre:<slug>` per source. Real-world spread this caught nothing wrong
on but proves depth: otakudesu 44 sources on one episode, anichin 284 episodes.

## 6. Does a scraper fix need a server restart? Check the execution pool
Extension-hub-pro runs scrapers in worker threads with IDLE AUTO-TERMINATE (2s) —
code edits take effect with zero restart. Contrast: long-lived in-process cached
scrapers (voratoon-api era) DO need kill+restart or stale data masks your fix.
Check `core/isolatedRuntime.js`-style pool semantics before reaching for restart.

## 7. Regression bar
94/94 via `node test/run-all.js` must stay green after scraper patches; rerun the
audit script from step 1 as the user-visible before/after.
