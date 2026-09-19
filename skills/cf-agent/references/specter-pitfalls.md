# SPECTER Pitfalls (real-world runs)

Bugs and misconfigurations encountered when actually using SPECTER against real
sites and the bundled mock server. The "15 bugs" in `testing-pitfalls.md` cover
test-suite dev; this file covers **runtime/operational** use.

## File path / import path (TOP-1 STALE PITFALL)

**Problem:** Old `cf-agent` skill (and many web docs) reference `~/cf_agent.py`
as a top-level file. That path **does not exist** anymore. The project was
restructured into a proper Python package.

**Wrong:**
```bash
python3 ~/cf_agent.py "URL" "goal"          # FileNotFoundError
python3 ~/specter/cf_agent.py "URL" "goal"  # FileNotFoundError
python3 ~/specter/specter/cf_agent.py ...   # FileNotFoundError
from cf_agent import AIWebAgent             # ModuleNotFoundError
```

**Right:**
```bash
# Run as package (always from ~/specter workdir or with -m)
cd ~/specter
python -m specter "URL" "goal" --allow DOMAIN

# Or import:
from specter import AIWebAgent
```

**Detection:** If you see `can't open file '.../cf_agent.py'` or
`ModuleNotFoundError: No module named 'cf_agent'`, the path is wrong. Use
`python -m specter`.

## Mock server not started before agent (ERR_CONNECTION_REFUSED)

**Problem:** Agent runs `Page.navigate` to `http://127.0.0.1:18801/hcaptcha`
before mock server is up. Result: `final_url=chrome-error://chromewebdata/`,
LLM hallucinates "ERR_CONNECTION_REFUSED" as the page content, no detection
runs.

**Fix:**
```bash
# 1. start mock in background, wait for /healthz
python -m specter --serve-mock --port 18801 &
MOCK_PID=$!
for i in {1..30}; do
  curl -sf http://127.0.0.1:18801/healthz >/dev/null && break
  sleep 1
done

# 2. THEN run agent
python -m specter "http://127.0.0.1:18801/hcaptcha" "register" --allow 127.0.0.1
```

**Clean shutdown:** `kill $MOCK_PID` (NOT `pkill -f` which can hit zsh subshell).

## "LLM keeps screenshot()ing when captcha is human_required"

**Problem:** When SPECTER detects hCaptcha/reCAPTCHA/Arkose and marks state
`HUMAN_REQUIRED`, the LLM planner can burn all remaining `max_steps` on
`screenshot()` actions instead of escalating to `finish()` or `wait`. Example
log from real run:

```
step 1: LLM action: screenshot()
step 2: LLM action: screenshot()
step 3: LLM action: screenshot()
step 4: LLM action: screenshot()
step 5: LLM action: screenshot()
=== run end: success=False steps=6 ===
```

**Fix (operational):** Use `max_steps=2` for detection-only runs. The point of
SPECTER is to detect, not to act. If you want to try submitting a form, write a
dedicated test fixture with a mock captcha (see `test_cf_agent_vision.py`).

**Fix (code):** If you control SPECTER source, add a `human_required` early-abort
in `plan_rule_based` and `plan_llm`: if `vision_verdict.challenge_visible and
provider in human_required_set and step >= 1: return finish("aborted_reason:
human_required")`.

## xkiro.com `/register` has NO captcha (false assumption)

**Problem:** Assumed real-world sites with login pages have hCaptcha/reCAPTCHA.
Tested `https://xkiro.com/register`:
- Body 57KB Next.js SSR HTML
- 2 forms (login + register)
- Register form fields: `email`, `password` (autocomplete=new-password), `referralCode`
- **Zero captcha markers**: no `data-sitekey`, no `<script src="...captcha...">`, no
  `g-recaptcha`, no `h-captcha`, no `turnstile`, no `cf-chl`
- POST `/api/auth/register` returns `403 {"message":"Origin không hợp lệ"}`
  (Vietnamese for "Invalid Origin")

**The actual gate is API-level Origin header check**, not client-side captcha.
Always inspect both the page AND the API before assuming a captcha is present.

**Workaround for xkiro.com:**
```python
import cloudscraper
scraper = cloudscraper.create_scraper()
r = scraper.post('https://xkiro.com/api/auth/register',
    data={'email': '...', 'password': '...', 'referralCode': ''},
    headers={
        'Origin': 'https://xkiro.com',
        'Referer': 'https://xkiro.com/register',
        'Content-Type': 'application/json',
    })
```

## Cloudflare Standard (free tier) is bypassable via HTTP-level

**Problem:** Assumed Cloudflare = strong protection. Tested
`https://xkiro.com/dashboard/api/keys` with all 3 modes of `cf_bypass.py`:

```
Mode 1 (curl_cffi impersonate):  ✅ Verdict: OK
Mode 2 (cloudscraper):           ✅ Verdict: OK
Mode 3 (curl + HTTP/2):          ✅ Verdict: OK
```

**Implication for users hardening their own site:** Cloudflare Standard with
just TLS fingerprinting is insufficient. To block these bypasses, you need:
1. **Bot Fight Mode** (Security → Bots → toggle on)
2. **WAF custom rule** with JA3/JA4 fingerprint blocks
3. **Turnstile** instead of (or in addition to) JS challenge
4. **Managed Challenge** with "I'm under attack" mode on sensitive paths

**For authorized testing of YOUR site:** `cf_bypass.py` will tell you the
weakness in seconds. Run it BEFORE and AFTER each hardening change to verify
the gap closed.

## SPECTER detection works for human_required providers (it's not a fail)

**False negative framing:** User: "hCaptcha bypass doesn't work, SPECTER is broken."

**Reality:** SPECTER correctly identified hCaptcha on mock with confidence
**0.95** (body markers: `hcaptcha.com/1/api.js`, `hcaptcha.com/captcha`,
`h-captcha`). State correctly classified as `HUMAN_REQUIRED`. Then it did
nothing — by design. This is a **success** for SPECTER, not a failure.

**Communication fix:** When a user asks "bypass hCaptcha", show them the
detection result FIRST and explain that detection ≠ solution. Then point them
to commercial solver APIs if they actually need bypass.

## Cloudflare-bypass script `cf_stealth.py` won't run in pure Termux

**Problem:** `cf_stealth.py` (cf_bypass gen 5) tries to launch Chromium with
`proot-distro login ubuntu`. On a stock Termux without proot installed, it
fails silently with:
```
chrome-stealth/launch_chrome.sh: line 28: chrome-stealth/chrome: No such file or directory
```

**Alternatives on pure Termux (no proot):**
1. **SPECTER package** (this skill) — uses bundled mock + CF auto-solve
2. **cloudscraper** — works for Cloudflare Standard only
3. **curl_cffi** with `impersonate='chrome110'` — works for Cloudflare Standard only

**To actually run `cf_stealth.py`:** need proot Ubuntu + Chromium ARM64 build +
~870MB RAM available. On 6GB Android, you can do it but each Chrome instance
eats ~400MB; run subtests in fresh subprocess.

## Background process management for mock server

**Problem:** Started mock server with `&` in foreground terminal got blocked by
the tool's safety filter. Re-issuing as `background=true` worked but
default-notify was off (silent daemon). On first run, the agent ran BEFORE the
mock was actually accepting connections.

**Pattern that works:**
```python
# 1. start in background, save PID
import subprocess
proc = subprocess.Popen(['python', '-m', 'specter', '--serve-mock', '--port', '18801'],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)

# 2. poll for readiness
import time
ready = False
for _ in range(30):
    try:
        r = subprocess.check_output(['curl', '-sf', 'http://127.0.0.1:18801/healthz'], timeout=2)
        if b'ok' in r.lower() or b'200' in r:
            ready = True; break
    except: pass
    time.sleep(1)
assert ready, "mock server not ready"

# 3. run agent
...
# 4. cleanup
proc.terminate(); proc.wait(timeout=5)
```

**For multi-task orchestration (cron, batch):** use `process(action="kill", session_id=...)`
in Hermes; do NOT use `pkill -f python` (catches your own shell).

## "Why is the page 0KB?" — check the mock-server log

When agent reports weird detection (UNKNOWN provider, 0 cookies), the issue is
usually that the mock server returned a redirect or 404. The mock-server log
(stdout) shows:
```
[mock] 127.0.0.1 "GET /favicon.ico HTTP/1.1" 404 -
```
which is harmless, but if you see `404 -` for your target endpoint, the URL is
wrong (typo, trailing slash, etc.).

**Diagnostic:** `curl -v http://127.0.0.1:18801/<endpoint>` and look at the
response status + body.

## Session hygiene between agent runs

**Problem:** After several SPECTER runs, `~/.cf_agent/sessions.db` accumulates
provider:host records. Detector cache in `cf_persistent` can carry stale
detection (5 min TTL). For reproducible tests, wipe between runs:

```bash
# nuclear option (all session state)
rm -rf ~/.cf_agent/runs/* ~/.cf_agent/sessions.db
# OR keep config, drop DB only
rm -f ~/.cf_agent/sessions.db
```

For real-bug investigations, the BEFORE-state in `trace.jsonl` is more useful
than the DB anyway.

## xkiro.com hCaptcha: page-level vs API-level enforcement (FULL VALIDATION)

**Initial assumption:** "xkiro.com /register has captcha in the page" — WRONG.
Page-level scan returned zero captcha markers. The captcha is enforced at
the **API backend**, not the SSR HTML.

**Discovery workflow that worked (xkiro.com 2026-09-02):**

1. **CSP header reveals backend host.** `GET /register` returned CSP with
   `connect-src 'self' https://api.xkiro.com wss://api.xkiro.com ...` —
   backend is `https://api.xkiro.com`, not `xkiro.com` itself.
2. **HCAPTCHA_SITEKEY found in JS chunks** (NOT in inline page HTML):
   `HCAPTCHA_SITEKEY:"f950cb8c-dc1e-4908-9378-43ead3ccc282"`.
3. **API endpoint discovery:** `fetch(${NEXT_PUBLIC_API_URL}/api/v1/auth/${o})`
   pattern in chunk `3-u2rky_4jt0t.js` revealed the `/api/v1/auth/` prefix
   (not just `/v1/auth/`).
4. **POST discovery to confirm enforcement:**
   - `POST https://api.xkiro.com/api/v1/auth/register` with email + password
     → `400 {"error":"BadRequestException","message":"Captcha verification failed. Please try again."}`
   - This is the **proof** that hCaptcha is enforced at the API, not the page.
5. **`cf_bypass.py` verdict on the public surface:**
   - `https://xkiro.com/dashboard/api/keys` → ✅ all 3 modes OK
   - `https://xkiro.com/register` (page HTML) → ✅ OK
   - `https://api.xkiro.com/api/v1/auth/register` (POST) → ❌ hCaptcha enforced

**Lesson:** When testing a site's protection, test BOTH the public page AND
the API endpoint. A page can look unprotected while the API enforces
server-side captcha. The cf_bypass HTTP-level tools only handle the page
path; the API will reject any submission without a valid captcha token.

**Recon script (xkiro.com-style, reusable):**
```python
import cloudscraper, re
scraper = cloudscraper.create_scraper()

# 1. Get page, extract CSP backend
r = scraper.get('https://example.com/register')
csp = r.headers.get('content-security-policy', '')
api_hosts = re.findall(r'https://([a-z\-\.]+\.example\.com)', csp)
print('Backend hosts:', set(api_hosts))

# 2. Find sitekey in JS chunks
chunks = re.findall(r'src="(/_next/static/chunks/[^"]+)"', r.text)
all_js = '\n'.join([scraper.get(f'https://example.com{c}').text for c in chunks])
sitekey = re.findall(r'HCAPTCHA_SITEKEY[:\s]+["\']([a-f0-9-]+)["\']', all_js)
print('hCaptcha sitekey:', set(sitekey))

# 3. Find API path patterns
paths = re.findall(r'["\'](/api/[^"\']+)["\']', all_js)
print('API paths:', sorted(set(paths))[:10])

# 4. POST to discover enforcement
for path in ['/api/v1/auth/register', '/api/auth/register']:
    r = scraper.post(f'https://api.example.com{path}',
        json={'email': 'x@y.com', 'password': 'Test1234!'},
        headers={'Origin': 'https://example.com', 'Referer': 'https://example.com/register'})
    print(f'{path}: {r.status_code} | {r.text[:200]}')
```

**Note on Next.js:** the path pattern in JS chunks often shows `/v1/auth/...`
but the actual route is `/api/v1/auth/...` (Next.js prepends `/api/` for
route handlers under `app/api/`). Always probe both forms.
