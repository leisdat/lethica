# cf_agent_vision — Vision abstraction

Layered on top of `cf_selenium` for screenshot-based classification, OCR, and challenge detection. Three providers with auto-fallback.

## File

- `~/cf_agent_vision/__init__.py` (532 lines, single-module package)

## API

```python
from cf_agent_vision import (
    VisionTask, VisionResult, VisionProvider,
    TesseractProvider, ClaudeVisionProvider, DomProvider,
    classify_page, get_vision, list_providers,
)

# Single provider
v = get_vision("tesseract")
r = v.analyze("challenge.png", task=VisionTask.OCR)

# Auto-pick + multi-provider merge
r = classify_page(
    snapshot=b.snapshot(include_html=True),
    png_path="/tmp/page.png",
    host="example.com",
    min_confidence=0.5,
)
print(r.label, r.confidence, r.provider)
```

## Provider priority

`get_vision()` auto-picks: **claude_vision > tesseract > dom**

`classify_page()` runs all enabled providers in parallel-priority order, returns first with `confidence >= min_confidence`, else best.

## Provider matrix

| Provider | API | Cost | Quality | Ready check |
|----------|-----|------|---------|-------------|
| `tesseract` | local binary | free | medium OCR | `shutil.which("tesseract")` |
| `claude_vision` | Anthropic API | paid | high | `os.environ["ANTHROPIC_API_KEY"]` |
| `dom` | CDP-only (no image) | free | medium for known markers | always ready |

## Install tesseract on Termux (not proot)

Proot Ubuntu is **too heavy** for Chrome + tesseract together (OOM on 6GB). Install directly in Termux:

```bash
pkg install tesseract  # 5.5.2 in Termux as of 2026-09
# Pillow already in Termux's site-packages
```

**DO NOT** try running tesseract from proot when Chrome is also running in Termux — proot steals ~600MB+ and OOMs.

## Tesseract usage pattern

```python
class TesseractProvider(VisionProvider):
    DEFAULT_PSM = 6  # uniform block — best for captcha text

    def analyze(self, image_path, task=VisionTask.OCR, ...):
        r = subprocess.run(
            [self.cmd, str(image_path), "-", "--psm", str(self.DEFAULT_PSM)],
            capture_output=True, text=True, timeout=30,
        )
        text = r.stdout.strip()
        return VisionResult(provider="tesseract", text=text, confidence=0.7 if text else 0.0)
```

**Pitfalls:**
- tesseract misreads are normal ("Verify you are human" → "Very youre human"). Don't trust exact text — use it for keyword presence.
- Empty text on dark/low-contrast images → confidence=0.
- `--psm 6` for captcha-style content, `--psm 11` for sparse text.

## DOM provider usage

`DomProvider.analyze_snapshot(snapshot, task)` — uses `cf_selenium.snapshot()` data (no image processing). Searches `headings`, `forms`, `buttons`, `accessibility` fields for marker strings.

**Body markers per provider** (kept in the per-provider detector files, but the DOM provider can also be used standalone):
- cloudflare: `"Just a moment..."`, `"cf-challenge"`, `"Verifying you are human"`
- recaptcha: `"g-recaptcha"`, `class*="grecaptcha"`, `id*="recaptcha"`
- hcaptcha: `class*="h-captcha"`, `id*="hcaptcha"`, `data-hcaptcha-widget-id`
- akamai: `id*="akamai"`, `class*="bm_"`, cookies containing `ak_bmsc`
- datadome: `id*="datadome"`, cookies `datadome`
- imperva: `id*="imperva"`, `class*="incap"`, cookies `incap_ses_*`
- aws_waf: `id*="aws-waf"`, cookies `aws-waf-token`

**Disambiguation gotcha**: `data-sitekey` is shared by both reCAPTCHA and hCaptcha — don't use it as a sole marker. Use class/id with provider-specific token.

## 6GB OOM management (CRITICAL)

Each Chrome instance eats ~400MB. With tesseract + Pillow loaded, total is ~500MB. On 6GB HP with mock server + 9Router + node services running, you have **~900MB-1.1GB free**.

**Subprocess-per-page pattern** (proven in `test_vision.py`):

```python
import subprocess, json, tempfile, time

def run_subtest(page_url, expected):
    """Each subtest is a fresh subprocess — Chrome memory freed on exit."""
    code = f"""
import sys, json
sys.path.insert(0, '/data/data/com.termux/files/home')
from cf_selenium import Browser
from cf_agent_vision import classify_page, VisionTask

b = Browser(profile='vision_subtest_{int(time.time())}', headless=True)
try:
    b.get('{page_url}')
    time.sleep(2)  # let JS settle
    png = b.screenshot()
    snap = b.snapshot(include_html=True)
    r = classify_page(snapshot=snap, png_path=png, host='{host}')
    print(json.dumps({{'ok': r.label == '{expected}', 'label': r.label,
                       'conf': r.confidence, 'provider': r.provider}}))
finally:
    b.quit()
"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True, timeout=120,
    )
    return json.loads(r.stdout.strip().splitlines()[-1])
```

**Pre-flight memory check:**

```bash
free -m | awk '/Mem:/ {print $7}'  # available column
# if < 800MB, kill mock server and sleep 5s before retry
```

## VisionResult shape

```python
@dataclass
class VisionResult:
    text: str = ""                # OCR text
    label: str = ""               # classification label
    confidence: float = 0.0       # 0..1
    elements: list[dict]          # [{label, bbox, confidence}] for ELEMENT_LOCATE
    provider: str = ""            # "tesseract" | "claude_vision" | "dom" | "none"
    raw: dict                     # provider-specific extras
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.error is None
```

## When to use which task

- `VisionTask.OCR` — just extract text (default)
- `VisionTask.CLASSIFY` — what is this? Returns `label` + `confidence`
- `VisionTask.CHALLENGE` — solve a visual challenge (e.g. "click all X") — **not implemented yet**
- `VisionTask.ELEMENT_LOCATE` — find coords of element — **not implemented yet**

## Test fixture

`~/test_vision.py` (193 lines) — runs each page in subprocess, saves screenshots + results to `~/test_logs/vision_test/`.

```bash
# Mock must be running on 18801
python3 ~/cf_agent_mock_server.py --port 18801 &
python3 ~/test_vision.py
# 3/3 PASS in ~60s on 6GB HP
```

## Out of scope (vision v2)

- Real-time CAPTCHA solving (no ML model, no commercial API yet)
- Visual challenge solving ("click all images with X") — needs Claude Vision + element bbox feedback
- Multi-frame video analysis
- Local CV (OpenCV template matching) — could add as a 4th provider
