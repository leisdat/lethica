# AI Browser Bot (~/ai-browser) — session 2026-08-25

Working Telegram bot that turns chat commands into web browsing + LLM
analysis. Built with python-telegram-bot v22, httpx + BeautifulSoup, and
Hermes CLI as the reasoning backend. All patterns below are verified working.

## Architecture

```
Telegram → bot.py (handlers) → engine.py (fetch/extract)
                              → bypass.py (multi-strategy fetch)
                              → llm.py (reasoning via `hermes chat -q ... -Q`)
                              → features.py (monitor loop, research)
                              → scraper.py (structured extraction)
                              → auditor.py (site audit probes)
                              → aipower.py (deep analysis, chat memory)
```

## Launch

```bash
cd ~/ai-browser && AI_BROWSER_BOT_TOKEN="<token>" TERM=dumb python3 bot.py
```
Must run via `terminal(background=true)`. Kill ALL old instances first —
`telegram.error.Conflict: terminated by other getUpdates request` means two
pollers share a token. `pgrep -f "bot.py"` matches its own shell wrapper;
verify each PID via `/proc/<pid>/cmdline` before killing.

## Commands (17)

/browse /read /links /ask | /search /research | /audit /monitor /monitors
/unmonitor | /translate /news /define /calc | /scrape /table /images |
/deep /chat /chatreset

## Bypass engine (bypass.py) — multi-strategy fetch

Sequential fallback until valid content:
1. basic (rotating UA)
2. full browser headers (Sec-Fetch-*, Upgrade-Insecure-Requests) — fixed
   Wikipedia mobile 403→200
3. mobile UA
4. reader proxy `https://r.jina.ai/<url>` — returns markdown text; mark
   result so callers skip HTML parsing

JS-only detection: SPA markers (`id="root"`, `__next`) + <500 chars visible
text after stripping script/style tags → `needs_js: True`. **Logic must be**
`needs_js or len(text)<200` — an earlier `and` version reported False for
empty Tokopedia pages.

**JSON API responses**: BeautifulSoup on JSON gives 0 chars of text.
Detect leading `{`/`[` in the body, `json.loads`, and return pretty-printed
JSON as the "text" field with strategy suffix `+json`. Without this the bot
cannot read any REST API.

Hotlink-protected image hosts need a `Referer: <page url>` header on download
(rawkuma/kuma.kyut.dev comic images returned HTML otherwise). Validate
`content-type: image/*` and >5KB before treating as a real image.

Send downloaded photos as `reply_media_group(InputMediaPhoto...)` (max 8);
fallback to single `reply_photo`.

## Reasoning via Hermes CLI (no API keys needed)

```python
proc = await asyncio.create_subprocess_exec(
    "hermes", "chat", "-q", prompt, "-Q",
    stdout=PIPE, stderr=PIPE, env={**os.environ, "TERM": "dumb"})
```
- `-Q` = quiet mode; strip metadata lines (`Session:`, `Title:`,
  `Duration:`, `Messages:`) from stdout to get just the answer.
- Timeout ~150s; deep analysis chains multiple calls so budget accordingly.
- Auth is Nous Portal OAuth managed by hermes itself — bots cannot reuse it
  as a static key, calling the CLI sidesteps token expiry entirely.

## Deep analysis pattern (aipower.py)

1. Fetch main page, extract links.
2. Score links by question keyword overlap (skip login/nav stopwords).
3. Fetch top 3 sub-pages (0.5s sleep between), cap each context at ~3500.
4. Combine all contexts (~14K chars max) into one LLM synthesis call.
5. Progress callbacks edit the Telegram message live (wrap in try/except —
   Telegram rate-limits identical edits).

## Monitor loop (features.py)

Monitors persisted to `monitors.json` ({id,url,keyword,chat_id,last_hash,
last_match}). Loop every 30 min: refetch page, compare sha256 of text,
alert on keyword line change or hash change. Skip alerting on first check
(baseline). Started via `asyncio.create_task(monitor_loop(app))` inside
`app.post_init`.

## Message formatting conventions (user preference)

User wants results "rapih dan enak dibaca":
- Header block: bold title, `┌ ├ └` tree for metadata, then `━━━` divider
- Numbered items with title/snippet/link on separate lines
- Long outputs split at 4000 chars; send overflow as files (CSV/TXT via
  tempfile + reply_document)
- Menu uses section emoji headers (🌐 🔍 🛠️ ⛏️ 🧠)

## Known gaps (documented, not fixed)

- JS-rendered sites (SPA): only detectable, not readable — user-facing
  warning added instead of silent empty results. Full fix needs headless
  Chromium which does not run in Termux.
- Reddit JSON API blocks all non-OAuth UAs (403 regardless).
- Playwright pip install fails on Termux (no matching distribution) — do
  not retry; use the hybrid request-based approach above.
