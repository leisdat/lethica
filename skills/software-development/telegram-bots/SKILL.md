---
name: telegram-bots
description: Use when building or running Telegram bots in Termux.
version: 1.1.0
---

# Telegram Bots in Termux

Class-level guidance for building long-running Telegram bots with
`python-telegram-bot` (+ aiohttp) on-device in Termux. Complements
`termux-dev` (which covers path quirks, previewing, verification).

## Setup
```bash
pip install python-telegram-bot aiohttp
pkg install yt-dlp        # only if downloader features are wanted
```

## Running (long-lived process)
- MUST run via `terminal(background=true)` — foreground calls that look like
  servers are rejected by the tool harness.
- **Only one instance per token.** Restart cycles commonly fail with
  `telegram.error.Conflict: terminated by other getUpdates request`. Fix:
  `ps -ef | grep <bot>.py`, kill every leftover PID (a previous kill may have
  spawned/restarted children), wait ~3s, then relaunch. Note `pgrep -f name`
  can match its own shell wrapper — verify with `ps -p <pid>`.

## Event-loop pitfalls (python-telegram-bot v22)
- Do NOT create `aiohttp.ClientSession()` at module import time — there is no
  running loop yet (`RuntimeError: no running event loop`). Create it in an
  `async def post_init(app)` hook passed to `Application.builder().post_init()`.
- If you define helper coroutines that reference the global session, declare
  `HTTP = None` at top level and assign inside `post_init`.
- Only ONE `post_init` hook is accepted; merge all startup work (session
  creation, spawning reminder loops via `app.create_task(...)` into it.

## DNS failure on Termux: `Errno 7: No address associated with hostname`
Symptom: bot loops `[tg] poll err: URLError: <urlopen error [Errno 7] ...>`
while general internet works. This is a **Python-resolver-only** breakage —
Android's network stack is fine.

**Diagnosis flow (do it in this order):**
1. `ping -c 2 8.8.8.8` → if OK, internet is fine, it's DNS.
2. `timeout 3 bash -c 'echo > /dev/tcp/149.154.167.99/443'` → if "Port 443 OPEN",
   TCP to Telegram works. NOTE: `ping` to Telegram IPs fails by design (ICMP
   dropped) — never conclude "network down" from a failed Telegram ping.
3. Do NOT bother with `$PREFIX/etc/resolv.conf` or `$PREFIX/etc/hosts` —
   Python/Android resolver ignores them; editing them does NOT fix Errno 7.

**Working fix — monkey-patch `socket.getaddrinfo` in the bot's HTTP wrapper module:**
```python
import socket
_TG_IPS = ["149.154.167.99", "91.108.56.138", "91.108.56.173"]
_TG_STICKY = [0]
_orig = socket.getaddrinfo
def _patched(host, port, *a, **k):
    if host != "api.telegram.org" or (a and a[0] == socket.AF_INET6):
        return _orig(host, port, *a, **k)
    last = OSError("no telegram IP available")
    for i in range(len(_TG_IPS)):
        idx = (_TG_STICKY[0] + i) % len(_TG_IPS)
        try:
            res = _orig(_TG_IPS[idx], port, *a, **k)
            _TG_STICKY[0] = idx  # sticky ke IP yang works
            return res
        except OSError as e:
            last = e
    raise last
socket.getaddrinfo = _patched
```
Keep the URL as `https://api.telegram.org/...` — only resolution is overridden,
so SNI and TLS cert verification stay intact. Never disable cert checks.

IP reachability varies per network — probe each candidate with
`timeout 3 bash -c 'echo > /dev/tcp/IP/443'` before trusting an entry.
Verified on user's device (2026-09-04): `149.154.167.99` OK, `91.108.56.138` OK,
`91.108.56.173` OK, `149.154.164.10` **TIMEOUT** (do not use as first entry).
Caveat: resolving an IP literal never fails, so the loop rotates only when the
resolver itself errors; a TCP-dead IP still surfaces as timeout/reset at connect
time — keep the list to probe-verified entries only.

## Launch & kill pitfalls
- If the bot file uses absolute package imports (`from agent.core import ...`),
  run it as a module from the PARENT dir: `cd ~ && python -m agent.tg_bot`.
  Running `python tg_bot.py` from inside the package dir gives
  `ModuleNotFoundError: No module named 'agent'`.
- NEVER pass a bot token inline in a terminal command line — secret redaction
  can replace part of it with a literal `…` (U+2026), producing
  `UnicodeEncodeError: 'ascii' codec can't encode character '\u2026'` inside
  urllib and a bot that polls forever with garbage auth. Pattern that works:
  write the token to `~/.hermes/agent_bot_token` (chmod 600) and have a
  launcher script do `export TELEGRAM_BOT_TOKEN="$(cat …)"` then `exec python -m …`.
  The token then never appears in any command line.
- `pkill -f "python tg_bot.py"` can match the invoking shell's OWN command
  line and kill itself (exit -15, no output). Correct cycle: `pgrep -f tg_bot`,
  verify each PID with `ps -o pid,args -p <pid>`, then `kill -9 <pids>`.
- After relaunch, old error lines remain in the appended log — trust only the
  lines after the newest `[tg-bot] starting…` marker.

## Callback data: the 64-byte limit
`callback_data` is hard-capped at 64 bytes. Slugs/titles longer than that get
silently truncated → later API calls 404. Pattern that works:

```python
SLUGS: dict[str, str] = {}          # short id -> full slug

def sid(slug):
    for k, v in SLUGS.items():
        if v == slug: return k
    k = f"k{len(SLUGS)+1}"; SLUGS[k] = slug; return k

def gid(short): return SLUGS.get(short)
```
Buttons carry `f"info:{sid(slug)}"`; handlers resolve back with `gid()` and
answer "data expired, search again" when lookup fails (bot restarts wipe the
in-memory registry).

## Media sending limits
Bot API sends max ~50 MB per file and media groups behave inconsistently with
large photo albums (400 Bad Request seen). Cap albums (~12 images) and offer
pagination buttons instead of one giant album.

## AI features without heavy libraries
`google-generativeai` / `google-genai` pip installs often FAIL on Termux
(maturin needs ANDROID_API_LEVEL; builds time out). Use the Gemini REST API
directly with aiohttp instead:
```
POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key=KEY
body: {"contents":[{"parts":[{"text": prompt}]}],
       "systemInstruction":{"parts":[{"text": sys}]}}
```
Response text: `j["candidates"][0]["content"]["parts"][0]["text"]`; image parts
appear as `inlineData.data` (base64). This avoids all native-build problems.

## Agent-bot UX: cheap chat by default, explicit task spawn
When the bot fronts an autonomous agent loop, do NOT treat every plain-text
message as a task goal — the user complained that "Halo" spawned a full
plan+exec+eval task with progress spam ("Chat bot nya masih kaya gini ya").
Design that was accepted:
- plain text → single LLM call with a small per-chat rolling history
  (deque ~12 msgs), strip `<think>`/`<think>` blocks from reasoning models
  before sending, pop the user msg on LLM failure so history stays paired;
- `/agent <goal>` (and `/plan`, `/agent --step`) → full task spawn;
- while a task thread is alive, route plain text and new goals into a prompt
  queue instead of answering or spawning (auto-drains when idle).
Also: env-var override beats the bot's `.env` auto-loader only if the loader
uses `if k not in os.environ` — check that before assuming `TELEGRAM_BOT_TOKEN=…
python …` will win over a stale `.env` value.

## User etiquette
- The user's bot may be in active use: get explicit go-ahead before killing,
  restarting, or patching a running bot; do read-only diagnosis first (user
  interrupted a mid-fix restart with "jangan di bot nya", 2026-09-04).
- Remind the user to `/revoke` the bot token at @BotFather if it was ever pasted
  into a chat/log.
- Bots die when the phone sleeps (Termux) — fine for testing; mention
  `termux-wake-lock` or a VPS for 24/7 uptime.

## Reference
See `termux-dev/references/lumen-api.md` for a real comic-content API used in
a working bot (search/genres/chapters/pages endpoints).

