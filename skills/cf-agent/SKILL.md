---
name: cf-agent
category: web
description: Build AI web-agents using cf_selenium with snapshot loop and multi-provider protection detection.
---

# AI Web-Agent (cf_agent.py)

## When to use

- Build AI web-agents that inspect pages and act on them
- Need snapshot → decide → act loop with execution trace
- Multi-provider protection detection (8 named providers + UNKNOWN sentinel)
- Screenshot-based challenge classification (OCR + DOM class signals, decision-only)
- Authorized staging testing only

## Project layout (current)

```
specter/
├── specter/                  # Main Python package
│   ├── __init__.py
│   ├── __main__.py           # CLI entry
│   ├── agent.py              # AIWebAgent class
│   ├── config.py             # BypassConfig + env overrides
│   ├── sessions.py           # BypassSession (namespace provider:host)
│   ├── tools.py              # Tool layer (extract/plan/browse/session)
│   ├── mock_server.py        # 20 endpoints (127.0.0.1 only)
│   ├── providers/            # 8 named adapters + sentinel
│   │   ├── __init__.py
│   │   ├── base.py           # ProviderAdapter + ProviderId + ChallengeState
│   │   ├── detector.py       # signature cascade + browser fallback
│   │   ├── registry.py
│   │   ├── cf_adapter.py
│   │   ├── aws_waf_adapter.py
│   │   ├── aws_waf_token.py  # token dataclass + persistent store
│   │   ├── akamai_adapter.py
│   │   ├── datadome_adapter.py
│   │   ├── imperva_adapter.py
│   │   ├── recaptcha_adapter.py
│   │   ├── hcaptcha_adapter.py
│   │   └── arkose_adapter.py
│   └── vision/               # Vision decision layer
│       ├── __init__.py
│       ├── claude_vision.py
│       ├── tesseract.py
│       └── dom.py
├── cf_selenium.py            # FROZEN — Selenium-style API + CF bypass
├── cf_persistent.py          # FROZEN — SQLite session/cookie store
├── tests/                    # Standalone test scripts
├── examples/                 # Runnable walkthroughs
└── README.md                 # Project docs
```

## Quick start (Python)

```python
from specter import AIWebAgent

with AIWebAgent(
    profile="agent",
    allowed_domains=["staging.example.com", "127.0.0.1"],
    authorized_test_mode=True,
    use_llm=True,  # uses routerku via HERMES_CUSTOM_127_0_0_1_20130_API_KEY
) as agent:
    result = agent.run("https://staging.example.com", "click the first product")
    print(result.summary, result.final_url, result.artifacts_dir)
```

## CLI

```bash
# observational goal (no action)
python -m specter "https://staging.example.com" "what is the title?" \
    --allow staging.example.com --no-llm --max-steps 2

# multi-step with LLM
python -m specter "https://staging.example.com" "click checkout, fill form" \
    --allow staging.example.com --max-steps 8

# start the bundled mock staging server (20 endpoints on 127.0.0.1:18801)
python -m specter --serve-mock --port 18801 &
```

**Always start mock server BEFORE running agent tests** — agent will fail with `ERR_CONNECTION_REFUSED` if it tries to navigate before mock is up. Check it's ready:
```bash
curl -s http://127.0.0.1:18801/healthz  # returns 200 + JSON status
```

## Config (priority: env > file > defaults)

```bash
# env overrides
CF_BYPASS_ENABLED=1
CF_BYPASS_ALLOW=staging.example.com,127.0.0.1
CF_AGENT_MAX_STEPS=15
CF_AGENT_MODEL=Free-All
CF_AGENT_CONFIG=~/.cf_agent/config.json
```

`~/.cf_agent/config.json`:
```json
{
  "bypass": {
    "enabled": false,
    "authorized_test_mode": true,
    "allowed_domains": [],
    "challenge_strategy": "auto_solve",
    "confidence_threshold": 0.6,
    "cache_ttl_seconds": 300
  },
  "llm": { "enabled": true, "model": "Free-All" },
  "agent": { "max_steps": 10, "headless": true }
}
```

## Multi-provider detection

8 named adapters in `specter/providers/`:

| Provider | auto_solvable | solve() | state |
|----------|---------------|---------|-------|
| cloudflare | ✓ | delegates to cf_selenium | turnstile/managed/js |
| akamai | ✗ | ProviderNotSolvableError | human_required (Bot Manager) |
| datadome | ✗ | ProviderNotSolvableError | captcha |
| imperva | ✗ | ProviderNotSolvableError | js_challenge |
| aws_waf | ✓ | token lifecycle | js_challenge |
| recaptcha | ✗ | **HumanRequiredError** | human_required |
| hcaptcha | ✗ | **HumanRequiredError** | human_required |
| arkose | ✗ | **HumanRequiredError** | human_required |

`UNKNOWN` is the sentinel (never registered; returned when confidence < threshold).

## Outputs

`~/.cf_agent/runs/<run_id>/`:
- `trace.jsonl` — one event per action
- `result.json` — final summary
- `screenshots/` — `step{N}_before.png`, `step{N}_after.png`

## Safety

- `bypass.enabled` defaults to **false** (must enable explicitly)
- `allowed_domains` required (no domains = blocked)
- `authorized_test_mode=True` is the only mode
- CF bypass only runs in this mode + on allowed domains
- UNKNOWN detection = no provider handler called
- Human-required providers (reCAPTCHA/hCaptcha/Arkose) → `HumanRequiredError` → agent stops
- ProviderNotSolvableError (akamai/datadome/imperva/aws_waf) → logged, agent continues

## Human intervention protocol

When `HumanRequiredError` is raised:
1. Agent stops immediately (success=False, error contains provider+message)
2. Trace event marked `aborted_reason: human_required`
3. User reviews trace + screenshot, opens URL in real browser, completes challenge
4. Re-run agent with `--allow` set, or feed cookies via cf_persistent manually

## Tested

**v6 (latest)**:
- ✅ hCaptcha/reCAPTCHA detection + helper flow (render widget, wait for user)
- ✅ Mobile Android fingerprint (Termux-friendly)
- ✅ Vision decision layer (DOM + Tesseract + Claude Vision)
- ✅ AWS WAF token lifecycle (store, load, invalidate, refresh)
- ✅ Multi-provider detection (8 named + UNKNOWN)
- ✅ Trace & screenshots per step
- ✅ Memory management for Termux 6GB

**v5**:
- ✅ End-to-end integration (vision + multi-provider + AWS WAF token + session)
- ✅ Test suite (9/9 PASS)

**v4**:
- ✅ Vision layer (DOM + Tesseract OCR + Claude Vision)

**v3**:
- ✅ Production-style tests (real cf_selenium + Chrome 130)

**v2**:
- ✅ Multi-provider detection (8 adapters)

**v1**:
- ✅ Cloudflare auto-solve + basic agent

## GitHub

https://github.com/letticha/specter