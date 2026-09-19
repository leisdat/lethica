# cf_persistent.py — Session persistence + smart fetch (deep reference)

Companion to `cloudflare-protection-testing` skill. The main SKILL.md covers
`cf_persistent.py` at a high level (gen 6). This file is the **build log** for
the session-persistence layer: architecture, the IIFE/fingerprint/cookie-class
pitfalls that hit while building it, and the validation test matrix.

Read this when you need to extend `cf_persistent.py`, debug a "session not
being reused" or "challenge re-appears every request" issue, or when designing
a similar persistent automation layer for a different anti-bot (Akamai, DataDome,
PerimeterX, etc.).

## Why this layer exists

Even with `cf_stealth.py` (gen 5) solving Turnstile cleanly, **every new
request that re-solves the challenge costs 15–30 seconds** (Chrome launch +
JS execution + cookie extraction). For a monitor running every 60s, that's
unacceptable. `cf_persistent.py` solves the challenge once, persists the
clearance, then serves subsequent requests via plain `curl_cffi` with the
stored cookies — measured **~1.5s per cached request** vs 20s+ for re-solve.

## Architecture (validated end-to-end)

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1: SQLite session store (cf_session.db)                   │
│  - sessions(host, ua, fingerprint_seed, cf_clearance,            │
│    cf_clearance_expires, cf_bm, last_challenge, last_used,       │
│    challenge_count, success_count)                               │
│  - cookies(host, name, value, domain, path, expires, …)          │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 2: Stable per-host fingerprint (fp_<host>.json)           │
│  seed = int.from_bytes(sha256(host)[:4], 'big')                  │
│  Same host → same fingerprint across all runs (canvas noise,     │
│  WebGL spoof, navigator props, screen, timezone, plugins).       │
│  CF sees the same "browser" → does not re-issue challenge.       │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 3: Persistent Chrome profile (/root/cf_persistent_profile)│
│  cookies, IndexedDB, cache retained across launches              │
│  combined with SQLite as the source of truth (Chromium cookies   │
│  are NOT directly queryable via Python; SQLite is)               │
└─────────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────────┐
│  Layer 4: Smart fetch (HTTP-only path, no Chrome)                │
│  1. db.is_cf_clearance_valid(host)? → if yes, use curl_cffi with │
│     stored UA + cookies, ~1.5s per request                      │
│  2. Invalid / first time → launch Chrome, solve, persist        │
│  3. Response 403/503 / has-challenge-markers → auto re-solve,    │
│     retry                                                       │
└─────────────────────────────────────────────────────────────────┘
```

## Sub-commands

```bash
python3 cf_persistent.py solve  https://host    # solve + persist (~15-30s)
python3 cf_persistent.py fetch  https://host    # reuse session (~1.5s)
python3 cf_persistent.py fetch  https://host --force  # force re-solve
python3 cf_persistent.py status                  # show all sessions
python3 cf_persistent.py monitor https://host --interval 60  # loop
```

## Two valid CF auth cookies — both must be checked

`cf_clearance` and `cf_bm` (or `__cf_bm`) are **two different** CF auth
cookies. `cf_clearance` is the long-lived clearance (15-30 min for normal
trust, up to 1 year for high trust). `cf_bm` is the Bot Management cookie
(typically 30 min, set on most CF-fronted pages even when no challenge is
shown). Many sites — including `www.cloudflare.com/cdn-cgi/trace` — only
return `cf_bm`, never `cf_clearance`.

If `is_cf_clearance_valid` only checks `cf_clearance`, every fetch to a
`cf_bm`-only host will re-solve unnecessarily. Both must be checked:

```python
def is_cf_clearance_valid(self, host):
    s = self.get_session(host)
    if not s: return False, 0
    now = int(time.time())
    # cf_clearance: explicit TTL stored in DB
    if s.get("cf_clearance") and s.get("cf_clearance_expires"):
        remaining = s["cf_clearance_expires"] - now
        if remaining > 300:                       # >5 min left
            return True, remaining
    # cf_bm: no explicit TTL in DB → derive from last_challenge/last_used
    if s.get("cf_bm"):
        last = s.get("last_challenge") or s.get("last_used") or 0
        if now - last < 1800:                     # 30 min from last seen
            return True, 1800 - (now - last)
    return False, 0
```

## Pitfall: text-based challenge detection → false positive

**Symptom**: on a page that mentions "turnstile" in marketing text (e.g.
`nopecha.com/demo` says "we test turnstile alternatives") the solver detects
a "challenge" that doesn't exist, logs `clicking turnstile` repeatedly,
never finds a widget, and times out without saving any session.

**Root cause**: the original challenge classifier used text markers in
body/title as primary signal:
```python
info["challengeType"] = (
    "turnstile" if info.get("hasTurnstile") or "turnstile" in haystack
    …
)
```
If body contains the word "turnstile" (even just in product copy), the
classifier labels it as turnstile — but `info["turnstileBox"]` and
`info["chlFrame"]` are both `null` because there's no actual widget. The
solver then keeps trying to click a non-existent box.

**Fix**: element-based detection is primary; text is fallback only for
**strong** markers that almost never appear in product copy:
```python
# Element-based FIRST
info["isChallenge"] = (
    info.get("hasTurnstile")
    or info.get("hasCfChallenge")
    or info.get("hasHcaptcha")
    or info.get("hasRecaptcha")
    or info.get("chlFrame") is not None           # actual iframe in DOM
    # weak text markers only as last resort
    or any(mk in haystack for mk in [
        "just a moment", "checking your browser",
        "verifying you are human", "attention required",
    ])
)
info["challengeType"] = (
    "turnstile" if info.get("chlFrame") is not None
    else "turnstile" if info.get("hasTurnstile")
    else "hcaptcha" if info.get("hasHcaptcha")
    …
)
```

Note the **strong marker list is much shorter** than the original — words
like "challenge" or "turnstile" appearing in body copy is normal. Only the
exact challenge-page phrases count.

## Pitfall: `sqlite3.Connection` has no `.description`

`Connection.description` is `None`. Only the **Cursor** has it. So:
```python
# BROKEN
r = c.execute("SELECT * FROM sessions WHERE host=?", (host,)).fetchone()
cols = [d[0] for d in c.description]   # ← AttributeError
return dict(zip(cols, r))

# WORKING
cur = c.execute("SELECT * FROM sessions WHERE host=?", (host,))
cols = [d[0] for d in cur.description]
r = cur.fetchone()
if r: return dict(zip(cols, r))
```

## Pitfall: `/tmp` is unwritable on Termux

Output paths like `/tmp/page.html` raise `FileNotFoundError [Errno 2]`
even when `/tmp` exists. Use `Path.home() / "filename"` or
`~/subdir/...` for any save-html / cache paths.

## Pitfall: stable fingerprint must come from a file, not in-memory

If `Fingerprint` regenerates its seed on every call (e.g. using
`random.seed(time.time())`), each solver run gets a different fingerprint
and CF sees it as a new browser → re-issues challenge → defeats the
whole point of persistence.

The fix is to **persist the per-host fingerprint to disk** and reload on
next call:
```python
class Fingerprint:
    def __init__(self, host: str):
        h = hashlib.sha256(host.encode()).digest()
        self._seed = int.from_bytes(h[:4], "big")
        self._cache_file = SESSION_DIR / f"fp_{host.replace('/', '_').replace(':', '_')}.json"
        if self._cache_file.exists():
            self.data = json.loads(self._cache_file.read_text())
        else:
            # deterministic generation from seed, then write
            self.data = self._generate(self._seed)
            self._cache_file.write_text(json.dumps(self.data, indent=2))
```

Same host → same seed → same fingerprint across all runs, regardless of
how many times `Fingerprint(host)` is constructed.

## Pitfall: keepalive WS ping is required during long solves

The browser-level WebSocket to `/devtools/browser/...` can be killed by
Chrome internal cleanup if no traffic flows for ~30s while a heavy JS
challenge is running. This is **not** an OS-level idle drop — Chrome itself
garbage-collects idle devtools sessions under memory pressure (and on a
6GB device, headless Chromium is always under memory pressure).

Fix: in the same loop that polls for cookies, send a lightweight
`Target.getTargets` ping every 2 seconds. The reader loop's response
dispatcher will already route it; the ping response contains
`{"id": <n>, "result": {"targetInfos": [...]}}` which can be discarded.

## Validation test matrix (this session)

| Target                              | First solve | Cached fetch | Re-solve triggered? |
|-------------------------------------|-------------|--------------|---------------------|
| `nowsecure.nl`                      | ✅ 18s      | ✅ 1.5s      | No (5/5 consecutive) |
| `www.cloudflare.com/cdn-cgi/trace`  | ✅ 16s (cf_bm) | ✅ 1.0s   | No                  |
| `nopecha.com/demo`                  | ✅ 15s (no challenge) | —   | No (page is just a demo) |

The `nopecha.com` test caught the text-based detection false positive that
motivated the "element-based first" fix above.

## Files layout on disk

```
~/.cf_persistent/
├── cf_session.db            # SQLite (sessions + cookies tables)
├── cf_profile/              # Chrome user-data-dir (persistent across runs)
├── cf_ua.txt                # last stable UA used
├── fp_<host>.json           # per-host fingerprint (seed + props)
├── page_<host>.html         # last rendered page (for debugging)
└── cf_persistent.log        # INFO-level log (set via logging.basicConfig)
```

## When to graduate beyond cf_persistent

If you find yourself with >50 hosts each needing its own session, the
SQLite-per-host model starts to bloat (~5KB per host × 50 = 250KB — fine
on disk, but the per-launch SQLite open and `is_cf_clearance_valid` query
adds ~50ms per request). For that scale, consider:

- Single SQLite DB at `~/.cf_persistent/cf_session.db` (current pattern,
  scales fine to ~10k hosts)
- LRU cache in front of `is_cf_clearance_valid` keyed by host
- Periodic cleanup of sessions with `success_count == 0` and
  `last_used > 30 days ago` (dead hosts)

For **enterprise Bot Management** (Crunchyroll, etc.) the entire
`cf_persistent.py` model is moot — no amount of session reuse helps
when the underlying detection is browser-fingerprint based and your
fingerprint is synthetic. Those need residential proxy + real Chrome
on a server with 8GB+ RAM.
