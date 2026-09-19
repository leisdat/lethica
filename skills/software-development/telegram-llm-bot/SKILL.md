---
name: telegram-llm-bot
description: Build or debug an LLM Telegram bot in Termux via hermes CLI.
---

# Telegram LLM Bot (Termux + Hermes backend)

Architecture for bots where Telegram messages are answered by an LLM without any
separate API key: the bot shells out to `hermes chat -q <prompt> -Q`, which handles
OAuth/model selection itself. Built and proven with the user's `~/ai-browser` bot
(19 commands + free chat).

## Stack

- python-telegram-bot v22 (`Application`, `CommandHandler`, `MessageHandler`)
- `httpx` + BeautifulSoup for web fetching inside bot commands
- State persisted as JSON files next to the script (monitors.json, rpg_saves.json)
- Run long-lived: `terminal(background=true)`; kill ALL old instances first

## LLM call pattern with fallback chain

```python
FALLBACK_CHAIN = [
    ("auto", []),                                                    # hermes default config
    ("nous", ["--provider", "nous", "--model", "stealth/ox-alpha"]), # free via OAuth
    ("bai",  ["--provider", "bai", "--model", "..."]),               # third-party key provider
]

async def _run_hermes(args, prompt, timeout):
    proc = await asyncio.create_subprocess_exec(
        "hermes", "chat", "-q", prompt, "-Q", *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "TERM": "dumb"})
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout)
    if proc.returncode != 0:
        raise RuntimeError(stderr.decode()[:150])
    # strip session metadata lines (Session:/Title:/Duration:/Messages:/session_id:)
```

- Detect quota/rate-limit errors (402/403/429/"credit"/"balance"/"not found") and fall
  through to the next chain entry; non-quota errors also fall through once.
- Tag each answer with the provider used (`_nous ✓_`) so the user sees what ran.
- Expose `/model <key>` (per-user override stored in a dict) and `/status`.

## Free-chat handler (no /command needed)

Register `MessageHandler(filters.TEXT & ~filters.COMMAND, handler)`. In the handler:
regex-detect URLs in the message → fetch that page and feed its text as context;
otherwise plain chat. Keep per-chat conversation memory (last N turns, in-memory dict)
so follow-ups like "yang tadi" work. Commands still take precedence automatically
because the filter excludes them.

## Pitfalls (all hit in practice)

- **Telegram `Conflict: terminated by other getUpdates request`** = two bot instances
  running. `pkill -f "python3 bot.py"` is not enough — loop over `pgrep -f` and check
  `/proc/<pid>/cmdline`, because pgrep matches its own wrapper shell. Wait 3s after kills.
- **ImportError after refactoring llm.py**: bot.py may hold duplicate `from llm import X`
  lines (one at top, one inline in a handler). Grep ALL import sites after renaming.
- **Vercel serverless must mirror every route** added to the local server.js — the #1
  source of 404s on production while localhost works.
- **CORS**: open APIs need explicit `Access-Control-Allow-Origin: *` middleware AND
  OPTIONS preflight exempted from rate limiting; browsers block otherwise.
- **Reader/gallery pages**: never put `loading="lazy"` on images inside a scroll
  container, and never set `document.body.style.overflow='hidden'` for overlays — both
  break scrolling on Android Chrome. Prefer normal document flow (`position:relative`,
  body scroll) over fixed-height scroll containers for long image lists.

## Web-fetching with bypass (for /browse-style commands)

Try strategies in order until real content appears: basic UA rotation → full browser
headers (Sec-Fetch etc.) → mobile UA → reader proxy (r.jina.ai). Detect JS-only SPA
shells (tiny visible text + `id="root"/"__next"`) and warn the user instead of returning
empty output. Also detect JSON responses before HTML-parsing so API endpoints are
readable.

## File layout (proven)

```
bot.py       # handlers, registration, monitor loop via app.post_init
engine.py    # fetch_page/search_web (bypass-aware, JSON-aware)
llm.py       # hermes CLI calls + fallback chain + per-user model state
features.py  # periodic checks (monitors), multi-source research
auditor.py   # parallel endpoint prober for site audits
scraper.py   # structured extraction: items, tables, images (+CSV export)
```