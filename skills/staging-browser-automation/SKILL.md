---
name: staging-browser-automation
description: Use when wrapping SPECTER for staging browser automation.
---

# Staging Browser Automation (brow.py pattern)

## When to use
- Need a thin `brow.py`/`brow_claim.py` over `specter.AIWebAgent` for an authorized staging domain
- Site is an SPA (click_link does not trigger navigation) — must `direct navigate` to href
- Login is Microsoft Entra ID B2C (`login.genspark.ai/.../oauth2/v2.0/authorize`) with Google/Microsoft/Apple + Login with email
- Need single-account session reuse (`~/.cf_selenium/cf_selenium.db`) instead of credential storage
- Need vision decision layer to distinguish `challenge_visible` vs `login_form` vs `none`

## File locations (2026-09-02 snapshot)
- Wrapper: `~/brow.py` — generic SPECTER wrapper (detect + vision, no hardcode creds)
- Single-account claim: `~/brow_claim.py` — reuse existing `profile=brow_claim` session, steps: check login -> Billing -> click Start Free Trial
- SPECTER package: `~/specter/` (`specter/agent.py`, `specter/providers/cf_adapter.py`, `specter/vision/`)
- Artifacts: `~/.cf_agent/runs/<run_id>/` (`trace.jsonl`, `result.json`, `screenshots/`, `vision_log`)
- Session DB: `~/.cf_selenium/cf_selenium.db` (cookies `cf_clearance/__cf_bm`, TTL 1800s–30d)

## Quick start
```python
from specter import AIWebAgent
with AIWebAgent(
    profile="brow",
    allowed_domains=["www.genspark.ai","login.genspark.ai","127.0.0.1"],
    authorized_test_mode=True,
    use_vision=True,
    use_llm=True,  # via routerku Free-All
) as agent:
    r = agent.run("https://www.genspark.ai/claw", "what is the title and is there a Log In link?")
    print(r.summary, r.final_url)
    # vision_log is on disk: Path(r.artifacts_dir)/"result.json" -> vision_log
```

```bash
# SPA-safe: extract href then direct navigate instead of click_link
python3 ~/brow.py "https://www.genspark.ai/api/login?redirect_url=https%3A%2F%2Fwww.genspark.ai%2Fclaw" --llm
# single-account claim (requires prior manual Google login once)
python3 ~/brow_claim.py
```

## Genspark Claw live findings (2026-09-02)
- `/claw` unauthenticated: title `Genspark`, OCR `Please log in to access Genspark Claw VM`, provider `unknown` (not CF), cookies 4→54 after vision steps
- `Log In` href: `https://www.genspark.ai/api/login?redirect_url=https%3A%2F%2Fwww.genspark.ai%2Fclaw` — SPA, `click_link` leaves `page_changed: false`, must direct navigate
- Login host: `login.genspark.ai/gensparkad.onmicrosoft.com/b2c_1_new_login/oauth2/v2.0/authorize?...client_id=536a4e98...` — Vision `login_form` conf 0.7, OCR shows `G Google | Microsoft | Apple | Login with email`
- Google OAuth (`accounts.google.com`) is bot-detected — full-auto `type` fails; `Login with email` is automatable, Google is human-only (1 click manual)
- Post-login check: `brow_claim.py` step1 extracts `Not logged in` vs logged-in state; if not logged in, instruct manual login then re-run (session reuse via profile)
- Single-account only — multi-email rotation is ToS abuse and gets all accounts/IP flagged

## Safety (inherited from SPECTER)
- `allowed_domains` required, `authorized_test_mode=True` only, `bypass.enabled` default false
- Vision is decision-only (never auto-solves/clicks on its own), `challenge_visible` conf threshold 0.6
- Never store passwords — use `.env` or manual OAuth, never hardcode creds
- HumanRequiredError for reCAPTCHA/hCaptcha/Arkose — stop and ask user to solve in real browser

## References
- `references/genspark-claw-2026-09-02.md` — full trace, screenshots, and Entra ID flow detail

## Pitfalls (from this session)
- `asdict(result)` does not include `current_provider` (agent attribute) — read `result.json` from disk for `vision_log`/`detection`
- `cf_selenium.snapshot()` needs `include_html=True` for DOM vision to see `cf-challenge`/`g-recaptcha` markers
- 6GB RAM: each Chrome+Tesseract ~500MB — run vision subtests in fresh subprocesses
- Click vs Navigate: always prefer `goto_url(href)` for SPA login links; `click_link` often no-ops
