# Testing pitfalls — bugs that cost real time in cf-agent dev

These are concrete traps that bit during production-style test development. Each one took 5-15 min to diagnose. Read before writing any test.

## 1. `b.cookies` returns ALL cookies in browser, not the page's cookies

`cf_selenium.Browser.cookies` calls `Network.getAllCookies` which returns **every cookie in the browser**, including cookies set by iframes loaded on the page.

**Symptom**: Testing `/hcaptcha` page, but detection reports `cf_clearance` → classifies as `cloudflare`. The mock server returns no cookies for `/hcaptcha`. Where do they come from?

**Cause**: The hCaptcha mock body contains `<iframe src="https://challenges.cloudflare.com/...">` which loads and sets `__cf_bm`, `__cflb` cookies via the iframe, even though no navigation to cloudflare happened.

**Fix**: Filter cookies by current URL's domain:

```python
from urllib.parse import urlparse
host = urlparse(b.url).hostname
relevant = {name: c for name, c in b.cookies.items()
            if host in c.get("domain", "")}
```

Or strip known CF cookies from detection:

```python
CF_COOKIES = {"__cf_bm", "__cflb", "cf_clearance", "_cfuvid", "cf_bm"}
cookies = [c for c in cookies if c not in CF_COOKIES]
```

## 2. Persistent Chrome profile + global SQLite session DB leaks cookies between tests

`cf_selenium.Browser` writes to a global `cf_session.db` SQLite at `~/cf_session.db` with table `sessions(host, cookies)`. The Chrome profile is at `cf_selenium_profile_{name}/` but **the SQLite is not namespaced** — host is the only key.

**Symptom**: Test 1 fetches `/cloudflare`, gets `cf_clearance` cookie, saves to DB. Test 2 fetches `/akamai` with `auto_solve=False`, but detection says "cf_cookies" — because the `cf_clearance` from test 1 is loaded back from the DB.

**Cause**: `_solve_if_needed` saves cookies after a CF solve. `Browser.__init__` may load them back on next launch.

**Fix**: Wipe both profile dir + SQLite before each subtest:

```python
import shutil, sqlite3
from pathlib import Path

def wipe_session(host):
    # 1. Chrome profile dir
    profile = Path(f"cf_selenium_profile_{profile_name}")
    if profile.exists():
        shutil.rmtree(profile)
    # 2. Global SQLite
    db = Path("cf_session.db")
    if db.exists():
        con = sqlite3.connect(db)
        con.execute("DELETE FROM sessions WHERE host = ?", (host,))
        con.execute("DELETE FROM cookies WHERE host = ?", (host,))
        con.commit()
        con.close()
```

Plus: **make each subtest use a fresh host** (cache-bust the URL path with a query param) so old cookies don't apply.

## 3. `b.snapshot()` does NOT return `html` by default

`b.snapshot(include_html=False)` is the default. HTML body is empty in the snapshot, so DOM-based detection that searches HTML body markers fails silently.

**Symptom**: DOM provider returns `label="normal_page"` for `/recaptcha` mock. The mock body has `<div class="g-recaptcha" data-sitekey="...">`. But snapshot's `html` is empty.

**Fix**: Always pass `include_html=True` for detection tests:

```python
snap = b.snapshot(include_html=True)
```

## 4. `snapshot["headings"]` etc. are lists of dicts, not strings

`b.snapshot()` returns structured fields like:

```python
{
  "headings": [{"text": "Cloudflare Mock", "level": 1, "tag": "h1"}],
  "forms": [{"action": "/login", "inputs": [...]}],
  "buttons": [{"text": "Submit", "selector": "..."}],
  "accessibility": [{"role": "button", "name": "Submit"}],
}
```

If your code does `"Cloudflare Mock" in snapshot["headings"]` it crashes with `TypeError: argument of type 'dict' is not iterable`.

**Fix**: Extract text from dicts first:

```python
headings_text = " ".join(h.get("text", "") for h in snap.get("headings", []))
if "cloudflare" in headings_text.lower():
    ...
```

## 5. `find_by_text` returns `<html>` element when no match found

When `Browser.find_by_text("Back to dashboard")` finds zero matches, it returns the root `<html>` element (default fallback). Clicking it does nothing.

**Symptom**: Test expects navigation after clicking "Back to dashboard" link. Click succeeds, but URL doesn't change.

**Fix**: Check that the returned element is actually the matched one:

```python
el = b.find_by_text("Back to dashboard")
# Verify it's a link, not the html root
if el.tag.lower() == "a":
    b._run(el.click())
```

Or use a more specific selector: `b.find("a:has-text('Back to dashboard')")` if such API exists, or just locate via href: `b.find('a[href="/dashboard"]')`.

## 6. `record()` wrapper hides async coroutines

`cf_selenium.Recorder._RecordedElement` wraps elements and routes calls through `_sync()` which may not await coroutines. Code like `b._run(el.click())` works, but `el.click()` (sync call) silently does nothing.

**Symptom**: Recording captures actions, replay fails — page never navigates.

**Fix**: Always use `b._run(el.click())` even when element is a `_RecordedElement` wrapper, because the wrapper's sync method may not actually execute the CDP call.

## 7. `result.provider` may be a `str`, not the `ProviderId` enum

When you have `class ProviderId(str, Enum)`, instances of `ProviderId.CLOUDFLARE` behave like both an enum AND a string. So `result.provider == ProviderId.CLOUDFLARE` works (enum compare), AND `"cloudflare" in result.provider` works (str-mixin).

**BUT** if someone wrote `result.provider = ProviderId.CLOUDFLARE.value` (assigning the string), then `result.provider.value` fails with `AttributeError: 'str' object has no attribute 'value'`.

**Pitfall**: The bug recurs in multiple adapters. Audit pattern:

```bash
# Find any place that assigns ProviderId.X.value to a typed field
grep -rn "ProviderId\.[A-Z_]*\.value" cf_agent_providers/
```

**Fix**: NEVER assign `.value` — assign the enum directly: `provider=ProviderId.CLOUDFLARE` (let str-mixin handle serialization).

```python
# ✅ correct
self.provider_id = ProviderId.CLOUDFLARE
# ❌ wrong (but compiles because of str-mixin)
self.provider_id = ProviderId.CLOUDFLARE.value
```

Same applies to `ChallengeState`. Also: `ProviderId("cloudflare") == ProviderId.CLOUDFLARE` returns True, so dict keys work either way.

## 8. `_ensure_chrome` doesn't reload if CDP is connected

`cf_selenium.Browser._ensure_chrome` only launches Chrome when `self._cdp is None`. So if you have a persistent Browser instance and call `b.get(url)`, it doesn't re-launch Chrome. The CDP connection persists across navigations — fine for most cases, but means a buggy previous nav can poison the next.

**Symptom**: Test 1 fails, test 2 inherits broken state. Wiping cookies doesn't help.

**Fix**: For test isolation, use a fresh Browser per subtest (`Browser(profile=f"test_{i}")`), not a shared Browser.

## 9. `human_click` uses Bezier mouse motion — slow, can miss target

The `human_click` action moves the mouse along a Bezier curve (anti-bot detection). On slow phones (6GB HP), this can be too slow (>5s per click) and the mouse can land off-target if the page scrolls mid-motion.

**Symptom**: Click "logs" as success but page doesn't navigate. Or click takes 5+ seconds.

**Fix for tests** (not for stealth): use the direct `click` or `js_click` action:

```python
# Slow, human-like
b._run(el.click())  # if click action is human

# Fast, direct
b._run(b.find("a#products-link").click())  # if it's the sync WebElement.click
# Or:
b._run(b.page.evaluate("document.querySelector('#products-link').click()"))
```

For real stealth production, use `human_click` with longer wait.

## 10. Mock server dies between sessions

Every gateway restart kills the background mock server. Re-launch before running tests:

```bash
pgrep -af cf_agent_mock_server  # check
# if not running:
python3 ~/cf_agent_mock_server.py --port 18801 &
sleep 2
curl -s http://127.0.0.1:18801/healthz | python3 -c "import sys, json; d=json.load(sys.stdin); print('endpoints:', len(d['endpoints']))"
```

## 11. `__ERR__:sent 1000 (OK); then received 1000 (OK)` is normal in detail logs

`b.url` after a click+redirect can return this error string from CDP if the WebSocket closes during the redirect. The actual final URL is in the context's `url_after_*` field recorded by the test orchestrator.

**Don't** treat this as a test failure. Check the test's evidence field, not the inline log line.

## 12. pyright nags on dynamic types but tests still run

`pyright` and `pylint` flag a lot of false positives when working with CDP, JSON dicts, and dataclass `field(default_factory=...)`. Tests run fine despite the warnings. **Don't waste time fixing pyright complaints unless the test actually fails.**

## 13. Each test that creates a Browser eats ~400MB — kill chrome between subtests

```python
import subprocess

def kill_chrome():
    subprocess.run(["pkill", "-f", "chromium"], check=False)
    subprocess.run(["pkill", "-f", "chrome"], check=False)
    time.sleep(1)
```

Use this between subtests that create separate Browser instances. The persistent profile lives on, but Chrome processes die.

## 14. Production-style test runner pattern

`~/test_prod_style.py` (528 lines) — 9 subtests, each with `TestContext` capturing artifacts (screenshots, HTML, result.json, evidence). Pattern:

```python
class TestContext:
    def __init__(self, name: str, run_id: str):
        self.name = name
        self.dir = Path(f"test_logs/{run_id}/{name}")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.evidence = {}

    def evidence_add(self, key, value):
        self.evidence[key] = value

    def __enter__(self):
        return self

    def __exit__(self, *args):
        (self.dir / "result.json").write_text(json.dumps({
            "test": self.name,
            "evidence": self.evidence,
            "passed": self.evidence.get("ok", False),
        }, indent=2))

# Usage:
with TestContext("01_login", RUN_ID) as ctx:
    b.get("http://127.0.0.1:18801/login")
    ctx.evidence_add("title", b.title)
    ctx.evidence_add("ok", "Dashboard" in b.title)
```

Run loop: `for name, fn in tests: with TestContext(name) as ctx: ok = fn(ctx)`.

## 15. Real-world site body markers must be specific

When testing against real public sites (example.com, iana.org, info.cern.ch, httpbin.org), don't use generic markers like "the project" or "WWW" — they may be absent from the homepage or exist in iframes.

**CERN example**: `http://info.cern.ch/` returns a 646-byte HTML with the actual content on a subpage `/hypertext/WWW/TheProject.html`. The homepage only says "http://info.cern.ch" as title.

**Fix**: Either test the subpage directly, or check the title in addition to body markers:

```python
expected_title = "Example Domain"
expected_body_marker = "illustrative examples"  # example.com

ok = (expected_title.lower() in b.title.lower() and
      expected_body_marker.lower() in b.html.lower())
```

## Summary checklist before running tests

- [ ] Mock server running on test port (`pgrep -af cf_agent_mock_server`)
- [ ] `free -m` shows ≥ 800MB available
- [ ] All stale Chrome processes killed (`pkill -f chromium`)
- [ ] Each subtest uses unique profile name + wipes cf_session.db
- [ ] `b.snapshot(include_html=True)` for detection tests
- [ ] Filter `b.cookies` to current host (strip CF cookies if irrelevant)
- [ ] Headings/forms extraction handles dict structure
- [ ] No `ProviderId.X.value` assignments (use enum directly)

---

# Vision-integration pitfalls (v4 cf_agent wiring)

These came up while wiring `cf_agent_vision` into `AIWebAgent.run()` as a decision layer. They are not covered above.

## 16. `b.html` is a `@property`, not a method

`cf_selenium.Browser.html` is declared as:

```python
@property
def html(self) -> str:
    if not self._cdp: return ""
    return self._run(self._cdp.js("document.documentElement.outerHTML", timeout=10))
```

Calling it as `b.html()` returns the property object (mypy complains "Object of type 'str' is not callable"), and `str()` of that is the value — not what you want for the HTML string. Or worse, your code reads a property object and you silently pass the wrong thing to DOM provider.

**Fix**: `b.html` (no parens) inside `vision_consult`. Always read once and cache if used multiple times.

## 17. `VisionProvider.analyze()` signature is `(image_path, task=...)` only

The base class declares `analyze(self, image_path: str, task: VisionTask.OCR, prompt="", timeout=30.0)`. There is **no `host` or `png_path` kwarg** in the base. Trying to pass them makes pyright angry and may silently pass them to `**kwargs` if any provider overloads.

**Symptom**: pyright reports "No parameter named 'host' / 'png_path'" everywhere you pass the dict snap or host to `analyze()`.

**Fix**: Each provider implements its own call. `DomProvider` overrides with `analyze_snapshot(snap, task=...)` that takes the dict. `TesseractProvider.analyze` takes `image_path: str` and ignores the snap. `ClaudeVisionProvider.analyze` also takes `image_path: str`.

```python
# DOM provider
if "analyze_snapshot" in type(dom).__dict__:
    r = dom.analyze_snapshot(snapshot, task=VisionTask.CLASSIFY)
else:
    r = dom.analyze(snapshot, task=VisionTask.CLASSIFY)  # fallback for non-DOM providers

# Tesseract / Claude Vision — pass PNG path string, not dict
r = tess.analyze(str(png_path), task=VisionTask.OCR)
```

## 18. `classify_page()` returns ONE VisionResult, not a dict of all providers

`classify_page()` in `cf_agent_vision` returns the **best single result** (early-return at threshold, else highest confidence). If you need to merge evidence from DOM + Tesseract (e.g. "DOM says cloudflare, Tesseract says recaptcha"), you can't get both from `classify_page()`.

**Fix**: Use `analyze_page()` which returns a `dict[str, VisionResult]` keyed by provider name (`"dom"`, `"tesseract"`, `"claude"`). Then merge manually:

```python
res = analyze_page(snap, png_path, host, use_tesseract=True, use_claude=False, use_dom=True)
dom_r = res.get("dom")
tess_r = res.get("tesseract")
# check both, fall back from DOM to Tesseract to Claude
```

If a provider is unavailable (Claude needs `ANTHROPIC_API_KEY`), the dict simply lacks that key.

## 19. DOM provider needs CSS class signals to disambiguate challenges

`DomProvider._classify()` looks for class names like `cf-challenge`, `cf-turnstile`, `g-recaptcha`, `h-captcha`, `cf-spinner`, `_abck`, `_pxhd`, `funcaptcha`. By default it pulls from `snap["accessibility"]` (CDP accessibility tree), but **`cf_selenium.snapshot()` does not return raw CDP accessibility** — it returns parsed headings/buttons/links without class info.

**Symptom**: `/cloudflare` mock with `<div class="cf-challenge-running">` — DOM provider returns `label="normal_page"` because no class signals were available. Vision falls through to Tesseract text matching, which only catches ~50% of cases.

**Fix**: cf_agent's `vision_consult()` enriches the snap with HTML before calling `analyze_page()`:

```python
if "html" not in snap and self.b is not None:
    snap = dict(snap)
    snap["html"] = self.b.html or ""  # property, see pitfall 16
```

Then `DomProvider._classify()` extracts class attributes from three places (in priority order):
1. `snap["accessibility"][].class` (raw CDP)
2. `snap["headings"][].class`, `snap["buttons"][].class` (cf_selenium parsed)
3. Regex `class="..."` on `snap["html"]`

If you add a new challenge type, add the class signal to all three sources, or just rely on the HTML regex.

## 20. Tesseract in proot Ubuntu OOMs when Chrome is loaded

First attempt: install Tesseract in proot (`proot-distro login ubuntu -- apt install tesseract-ocr`). Then bridge from Termux Python: `subprocess.run(["proot-distro", "login", "ubuntu", "--", "tesseract", ...])`.

**Symptom**: Each vision subtest OOM-killed at SIGKILL when running from proot. Proot Ubuntu spawns extra kernel libs that steal ~200MB on top of Chrome's 400MB. On a 6GB HP with 1GB available, it dies.

**Fix**: Install Tesseract directly in Termux, not in proot:

```bash
apt install -y tesseract   # installs 5.5.2 in /data/data/com.termux/files/usr/bin/
```

Then `subprocess.run(["tesseract", ...])` from Termux Python. No proot, no kernel overhead. Verifies with `tesseract --version 2>&1 | head -1` → `tesseract 5.5.2`.

Same pattern applies to Pillow: proot's `python3-pil` works, but Termux's Pillow is faster (no proot syscall layer).

## 21. `AgentResult` is a dataclass — can't `result.get("key")`

`AIWebAgent.run()` returns an `AgentResult` dataclass. After `asdict(result)` it becomes a dict, but the original object has no `.get()` method.

**Symptom**: `result.get("vision_log")` raises `AttributeError: 'AgentResult' object has no attribute 'get'`. You wrote the test against the in-memory return, but the actual `vision_log` was only attached when writing to disk.

**Fix**: Either (a) read from the on-disk `result.json`:

```python
result_file = Path(f"~/.cf_agent/runs/{run_id}/result.json")
if result_file.exists():
    on_disk = json.loads(result_file.read_text())
    rdict["vision_log"] = on_disk.get("vision_log", [])
```

Or (b) attach `vision_log` to the dataclass as a regular field set during the run, so it survives in memory.

Pattern (a) is what `test_cf_agent_vision.py` uses. Pattern (b) is cleaner if you need the in-memory access.
