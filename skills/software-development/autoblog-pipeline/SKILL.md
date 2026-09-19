---
name: autoblog-pipeline
description: Autoblog pipeline, AI articles to static blog via git push.
---

# Autoblog Pipeline (AI articles → static blog on Vercel)

Proven end-to-end in `~/autoblog` (pipeline.py) + `~/autoblog-blog` (repo) with the
pipeline wired into the AI Browser bot (`/newarticle` in `~/ai-browser/bot.py`).
Live example: https://ngopigame-blog.vercel.app

## Architecture (the part that WORKS)

```
Telegram /newarticle → riset topik (DuckDuckGo search_web)
  → fetch 2-3 sources (fetch_page) + hero image (extract_og_image)
  → AI tulis artikel HTML (llm._query_with_chain)
  → publish_to_blog(): update posts.json + write posts/<slug>.html
  → git add/commit/push → GitHub → Vercel auto-deploy → live
```

File layout of the static blog repo:
- `index.html` — reads `posts.json` via fetch, renders article cards
- `posts.json` — `[{title, date, slug, excerpt, content, image, provider}]`
- `posts/<slug>.html` — full article page (generated from a Python template)
- `images/<slug>.<ext>` — hero images (og:image downloaded from sources)

## v3 URL-First + 3 Layers (2026-08-28, user's required architecture)

User mandated (after index-title hallucination): pipeline MUST be URL-first —
index/RSS only finds URLs; the bot OPENS each original article and writes ONLY
from verified full-article content. Implemented in `run_new_article_pipeline()`:

```
RSS feeds (detik/kompas/cnn — _RSS_FEEDS, shuffled per-day)
  → _rss_article_urls() / _extract_article_urls() (index crawl fallback)
  → fetch_page(url) + min 400 chars
  → LAYER 1 _classify_article(): AI JSON {main_topic, is_news_article,
    confidence>=0.7} — homepage/tag/search/livescore/ads/listicle → ⛔ INVALID
    (fail-closed: AI call fails → INVALID → STOP)
  → LAYER 2 _extract_facts() from VALID articles only → writer constrained to facts
  → LAYER 2b _fact_check_pass(): every important number in the HTML must appear
    in facts (>30% untraceable numbers → STOP, human review)
  → LAYER 3 _is_duplicate_article(): title Jaccard>=0.6 OR classifier main_topic
    Jaccard>=0.7 OR identical score token ("2-0") + >=0.4 team-word overlap
  → publish (old v2 flow)
```

Hard-won gotchas (all hit in live E2E):
- `engine.fetch_soup` returns a **4-tuple** `(soup, final_url, strategy, needs_js)` —
  unpacking only `soup` throws inside try/except and silently empties the extractor.
- Search results include **voucher/promo/product pages** (detik webvoucher...) and
  homepage/section pages — `_GARBAGE_PATH_WORDS` + path-length >= 20 filters them;
  Layer 1 still catches what slips through.
- `_title_tokens` was letters-only, so score identity ("2-0") was lost → dedupe
  missed "Menang 2-0" vs "Taklukkan 2-0". `_score_tokens()` extracts `N-M/N:M`.
- bot.py `_query_with_chain` wrapper must be `async` + pass through `quick=` —
  llm's real chain is async and returns a tuple.
- E2E test WITHOUT publish: stub `telegram`/`telegram.ext` as bare ModuleTypes
  (also `ContextTypes.DEFAULT_TYPE` as a class attr, `filters.TEXT`, `Update`,
  `Bot`, `Message`) then call `run_new_article_pipeline()` directly.
- Bot cmdline on this box is `python3 /…/python3 bot.py` — match `*bot.py*` on the
  FULL cmdline, not `python3 bot.py` prefix.
- 9Router (next-server) may answer slowly right after boot — first curl can time
  out (000) while the server is actually fine; retry before restarting anything.

## v2 Features (2026-08-28, all in `~/ai-browser/bot.py`)

- **Style writer (Switch n8n)**: `/newarticle --style=berita|analisis|listicle|opini <topik>` —
  `ARTICLE_STYLES` dict swaps struktur prompt; default `berita`.
- **Dedupe (Cek Database n8n)**: `_recent_titles(96h)` + Jaccard token similarity
  (`_is_duplicate`, threshold 0.6) vs posts.json. Duplicate → guard + `/autoblog force`
  publishes `_LAST_ARTICLE` anyway.
- **AI image fallback (Generate Gambar n8n)**: `_generate_ai_image()` via Pollinations
  (GRATIS, no key) — `https://image.pollinations.ai/prompt/<q>?width=1024&height=576&nologo=true&seed=...`,
  reject < 8KB. Used only when sources give no og:image.
- **Auto index (Auto Index Google n8n)**: `_update_sitemap_and_indexnow()` regenerates
  sitemap.xml (git push) + pings api.indexnow.org (Bing/Yandex/Seznam). Key file MUST be
  deployed at site root: `~/autoblog-blog/indexnow-key.txt` → live at /indexnow-key.txt.
  Google crawls via sitemap; IndexNow covers Bing-side.
- **AUTO daily**: `auto_daily()` + `/autoblog now|force|style|status`. Cron Hermes job
  `529f3df476f1` 07:00 WIB runs `~/autoblog/auto_run.py` (chat_id=None — cron message
  IS the notification, don't double-send via _tg_notify).
- Bot token persisted at `~/ai-browser/.bot_token` (chmod 600), auto-loaded by bot.py
  when env var absent — restarts no longer need manual token.

## ⚠️ Do NOT use WordPress.com for this (hard-won 2026-08)

WP.com free plan CANNOT post via REST API with Basic Auth + Application Password:
- `public-api.wordpress.com/rest/v1.1/...` → 403 `"User cannot edit posts"` even when
  the user IS Administrator and the site IS launched. Capabilities come back empty.
- `wp-json/wp/v2` on WP.com-hosted sites → 404 (returns HTML, not JSON).
- `/me` → 403 `authorization_required` ("An active access token must be used").
- App passwords on WP.com only work for XML-RPC / login flows, not REST write.
- Jetpack connection is required for Basic Auth REST on WP.com-hosted sites, and even
  then the wp-json endpoints stay 404 on free plan.
- `launch_status: unlaunched` / `is_coming_soon: true` additionally blocks writes —
  but fixing that does NOT fix the auth problem.

**Decision: static blog (GitHub Pages/Vercel) via git push is the reliable zero-cost
path on Termux.** `vercel` auto-deploys every push to `main` — no auth dance at all.
For a CMS-like API instead, use Ghost or self-hosted WP on a VPS, not WP.com free.

## Integrating into an existing python-telegram-bot

The pipeline functions must be **async** and awaited inside the bot's event loop:

- ❌ `asyncio.get_event_loop().run_until_complete(...)` inside a handler →
  `RuntimeError: This event loop is already running`.
- Make `find_topic`, `write_article`, `run_new_article_pipeline` all `async def` and
  `await` them. `fetch_page` / `search_web` / `extract_og_image` from `engine.py`
  are already async — await directly.
- `llm._query_with_chain(prompt, chat_id, quick=True)` returns a **tuple** `(answer, provider)`.
  `llm.free_chat` returns a plain **string**. Wrapping free_chat in a "query_chain"
  and unpacking 2 values → `ValueError: too many values to unpack (expected 2)`.
  Import the real `_query_with_chain` from llm, never fake it with free_chat.

## Pitfalls

- **Git branch**: Vercel repo may default to `main`; hardcoding `git push origin master`
  fails with `src refspec master does not match any`. Check `git branch` / use `main`.
- **Excerpt must be tag-stripped**: `article['html'][:200]` slices mid-`<p>` and the
  unclosed tag swallows following content in the browser. Strip tags first
  (`re.sub(r"<[^>]+>", " ", html)` then collapse whitespace) into a clean excerpt.
- **Hero images**: `extract_og_image(url)` → og:image meta → twitter:image → first
  large `<img>` in article/main. Download with a UA header, save as
  `images/<slug>.<ext>`, skip files < 5KB. Some sources return logo fallbacks —
  try multiple sources; a failed image must never fail the article (None is fine).
- **Old posts backfill**: articles generated before the image feature have no image —
  write a one-off script: search_web(title) → extract_og_image → download → prepend
  `<figure><img...></figure>` to content → regenerate post HTML.
- Multiple `python3 bot.py` instances → Telegram `Conflict: terminated by other
  getUpdates request`. `pgrep -f "bot.py"` also matches other bots with the same
  filename in different dirs — verify with `readlink /proc/<pid>/cwd` before killing.
- **Orphan child trap**: `process kill` on a background session only kills the bash
  WRAPPER — the python child keeps polling and re-triggers Telegram Conflict. Always
  `kill -9 <python-pid>` directly (find via `pgrep -af bot.py`, verify cwd).
- **Inline image injection MUST be block-boundary + depth-aware.** Naive
  `re.split(r'(?=</?p|h2|...)')` splits OPEN and CLOSE tags into separate fragments,
  so a `<figure>` can land INSIDE `<p>`/`<ul><li><p>` — browsers "repair" the invalid
  HTML and DROP content (a full "## Transfer" list vanished) and duplicate figures
  appear glued to headings. `_inject_images()` in bot.py now matches whole
  `open…close` blocks AND tracks container depth (ul/ol/li/figure/table) — only
  inserts at depth 0. Replay-fix for an already-published bad post: strip all
  figures with regex, re-add hero, re-inject, rewrite posts.json + post HTML, push.
- **Scraped images are often IRRELEVANT** (user complaint "ilustrasinya gak nyambung"):
  sources are frequently TAG/INDEX pages (`/tag/`, `/tags/`, `/topik/`, `/arsip/`...)
  mixing many other news + watermark graphics ("Jernih Melihat Dunia" Kompas banners).
  Fixes in bot.py: `_is_tag_page()` skips image extraction from tag/index pages (text
  still used), `_looks_like_editorial_graphic()` filters watermark/branding URLs, and
  inline illustrations are now **AI-generated per section** (`_section_heads` →
  `_generate_ai_image(prompt dgn heading, suffix=_s<i>)` → `_inject_sections` places
  each figure EXACTLY after its h2/h3 with caption "Ilustrasi: <heading>"). Scraped
  photos only as fallback per section. Never bulk-inject scraped images.
- **AI writers emit empty sections**: prompt says "skip if no facts" but models still
  output bare `<h2>Transfer Terbaru</h2>` — `_strip_empty_sections()` (runs at
  publish) deletes h2/h3 immediately followed by another heading or end of content.
- **Hardcoded dates rot**: article prompt had "26 Agustus 2026" baked in — now
  `time.strftime('%d %B %Y')`. Keep dates dynamic.
- Termux: `hermes gateway start` unsupported — gateway must run manually
  (`hermes gateway` in background); cron jobs won't fire without it.

## Design preferences (user letticha — DO NOT ship plain)

User rejects generic/plain designs ("masih putih bersih", "polos GK profesional",
"text masih standar"). Required bar for the blog front-end:
- **Dark/light toggle button** (manual, persisted in localStorage) — not just
  `prefers-color-scheme` auto.
- Editorial magazine style: serif display font for headings (Newsreader / Playfair
  Display), Inter/Roboto body, JetBrains Mono for kickers/labels.
- Glassmorphism sticky header, gradient blobs / accent gradient, card hover lift +
  shadow, drop cap on first paragraph, article cards with 16:9 thumbnails.
- Generate the design system via the `ui-ux-pro-max` skill's search script
  (`--design-system`) rather than inventing tokens ad hoc.

## Verification

```bash
curl -s https://<project>.vercel.app/ | grep -c 'data-theme\|theme-toggle'
curl -s https://<project>.vercel.app/posts.json | python3 -m json.tool | head
curl -s -o /dev/null -w '%{http_code}' https://<project>.vercel.app/images/<slug>.png
```
Push → wait ~10-20s for Vercel build → re-curl. Also `git push origin main` then
`git ls-remote origin` to confirm the commit landed.
