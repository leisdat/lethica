# Lethica web/memory/plan tools — implementation notes (v1.1–v2.0, live-tested 2026-09-08)

All zero-dep (urllib + base64). Canonical source: `~/lethica/lethica.py`.

## web_search — Bing primary, DDG lite fallback

### Why Bing first
DDG lite rate-limits by IP: after a few rapid queries it serves an "anomaly" challenge
page (~14KB, zero `result-link` anchors, `anomaly.js?...cc=botnet` iframe). No cookie
workaround (cookiejar retry still blocked). It recovers after minutes — treat as
fallback only. Bing works reliably with a plain mobile UA.

### Bing parser (current markup, 2026)
```python
UA = "Mozilla/5.0 (Linux; Android 13) ... Chrome/124.0 Mobile Safari/537.36"
req = urllib.request.Request(f"https://www.bing.com/search?q={quote(q)}&count={limit+5}",
                             headers={"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9"})
page = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")

for c in re.split(r'<li class="b_algo"', page)[1:]:
    # NEW markup: <a href="URL"><h2>Title</h2></a>   OLD: <h2><a href>title</a></h2>
    h2 = (re.search(r'<a[^>]*href="(http[^"]+)"[^>]*>\s*<h2[^>]*>(.*?)</h2>', c[:3000], re.DOTALL)
          or re.search(r'<h2[^>]*>\s*<a[^>]*href="(http[^"]+)"[^>]*>(.*?)</a>', c[:3000], re.DOTALL))
    if not h2: continue
    url, title = h2.group(1), re.sub(r"<[^>]+>", "", h2.group(2)).strip()
    # decode bing redirect: bing.com/ck/a?...&u=a1<base64url-of-target>
    if "bing.com/ck/a" in url:
        um = re.search(r"[?&]u=a1([^&]+)", url)
        if um:
            tok = um.group(1).replace("-", "+").replace("_", "/")
            tok += "=" * (-len(tok) % 4)
            try:
                dec = base64.b64decode(tok).decode("utf-8", "replace")
                if dec.startswith("http"): url = dec
            except Exception: pass
    snm = re.search(r"<p[^>]*>(.*?)</p>", c, re.DOTALL)  # snippet in first <p>
```

### DDG lite parser (fallback)
`GET https://lite.duckduckgo.com/lite/?q=...` → anchors `a.result-link` carry DIRECT
urls now (no `uddg=` redirect) — but still keep the uddg unquote branch for when DDG
serves the redirect form. Snippets in `td.result-snippet` following each link.

## browse — cookie-jar session

```python
COOKIE_JAR = {}   # domain -> {name: value}
LAST_URL = [None]

# send:  header Cookie = "; ".join(f"{k}={v}" for k,v in COOKIE_JAR[domain].items())
# store: for hv in resp.headers.get_all("Set-Cookie") or []:
#            k, v = hv.split(";")[0].split("=", 1)
#            drop if v in ("", "deleted") else COOKIE_JAR.setdefault(domain, {})[k] = v
```
- Page extraction: take `<body>`, drop `<script|style|noscript>`, `<br>`→`\n`, closing
  `</p|div|tr|li|h1-6>`→`\n`, strip tags, collapse whitespace; truncate 4000 chars.
- Also emit first 30 `<a href>` links (relative ok — resolve with `urljoin(LAST_URL)`).
- POST form data: `data="a=b&c=d"` → body utf-8, Content-Type urlencoded.

## memory bank

- One markdown file per entry in `~/lethica/memory/<safe-key>.md` (key sanitized `[a-zA-Z0-9_-]`, ≤80 chars).
- Actions: save / load (one or list-all) / search (regex over all entries, 30-hit cap) / forget.
- `memory_bank_summary()` lists entry names (cap 40) → injected into system prompt on every `build_system_prompt()` so the model knows what exists without loading.

## plan mode

- Single active file `~/lethica/workspace/plans/active-plan.md`.
- `save` replaces, `append` adds lines (checkbox updates), `show`, `clear`.
- Injected into system prompt (first 1500 chars) on build/restart — model self-tracks progress.

## config.toml loading (stdlib tomllib + fallback)

```python
def load_config():
    try:
        import tomllib
        with open(CONFIG_FILE, "rb") as f: return tomllib.load(f)
    except ImportError:
        # mini parser: [section], key = "value"/int/bool, strip inline #comments
```
- Auto-write DEFAULT_CONFIG template if file missing (first run bootstrap).
- Hot-reload in `/config` handler: `global` declarations must be FIRST line of `main()`
  (SyntaxError otherwise), then re-read config, reassign module globals, rebuild sysprompt.

## hy3 / reasoning-model behavior (routerku Free-All)

- `max_tokens` too small (e.g. 30) → `content: ""`, `finish_reason: "length"`, all tokens
  consumed by `reasoning_content`. Use ≥512 for chat, and in the loop fall back:
  `reply = msg.get("content") or msg.get("reasoning_content") or "(empty reply)"`.
- Live test: `chat("Free-All", [{'role':'user','content':'balas satu kata: siap'}], max_tokens=512)` → `"Siap."`
