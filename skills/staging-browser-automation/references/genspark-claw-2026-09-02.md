# Genspark Claw — Live Test 2026-09-02

## Runs
- `run_1788311619_6c9b` — `GET /claw` no-LLM, 11 vision consults, `challenge_visible=False` conf 0.0, OCR `Please log in to access Genspark Claw VM` from step6 onward, provider `unknown` (not Cloudflare), cookies 4→54, title `Genspark`, `page_changed` true at steps 5–7 as JS hydrated.
- `run_1788311743_180e` — same URL with `--llm`, LLM extracted `{"text":"Log In","href":"https://www.genspark.ai/api/login?redirect_url=https%3A%2F%2Fwww.genspark.ai%2Fclaw"}`, clicked 4x but `page_changed:false` (SPA quirk).
- `run_1788311962_80c3` — direct navigate to `login` href with `--llm`, landed `login.genspark.ai/gensparkad.onmicrosoft.com/b2c_1_new_login/oauth2/v2.0/authorize?client_id=536a4e98...`, title `Sign up or sign in`, vision `login_form` conf 0.7, OCR `G Google | Microsoft | Apple | Login with email`, LLM verdict `Google login button: Yes, Plus trial: No`.
- `run_1788312348_464a` — `brow_claim.py` single-account check, correctly reported `Not logged in` (profile separation from phone Chrome).

## Entra ID B2C Flow
```
/claw --Log In--> /api/login?redirect_url=/claw --302--> login.genspark.ai/.../b2c_1_new_login/oauth2/v2.0/authorize?client_id=536a4e98-fd24-4cbc-a67b-417e209e0080&response_type=code&redirect_uri=https://www.genspark.ai/api/auth&scope=email offline_access openid profile&prompt=login
   |
   +--> options: G Google | Microsoft | Apple | Login with email | Login with SSO
   +--> Google -> accounts.google.com (bot-detected, humanRequired)
   +--> Login with email -> automatable (fill email/pass, submit, no bot check)
```

## SPA Navigation Pitfall
- `click_link "Log In"` via AIWebAgent rule/LLM planner does not navigate on Genspark SPA — trace shows `duration_ms 6` and `page_changed:false` for 4 consecutive clicks.
- Fix: extract `href` from `extract:all` links array, then `goto_url(href)` / `agent.run(href, ...)` for direct navigation.

## Session Reuse
- Chrome profile `brow_claim` stores cookies in `~/.cf_selenium/cf_selenium.db` and `~/.cf_agent/sessions.db` (namespaced `provider:host`).
- Phone Chrome vs Termux Chrome are separate profiles — reusing requires either manual login in Termux once or cookie import.
- After manual Google login, `brow_claim.py` step1 checks `Log In` presence to decide whether to proceed to Billing.

## Vision Verdicts
- `/claw`: `none` conf 0.0 (no CF), tesseract picks up nav chrome (`New | Claw | Home | Bran | More | Loading...`)
- `/login` (Entra): `login_form` conf 0.7 via `dom` + `tesseract` (sources), latency 829–979ms

## Safety Notes
- Single-account only. Multi-email rotation to farm Plus trials violates ToS and triggers fingerprint + Entra ID flagging (all accounts + IP banned).
- Never automate `accounts.google.com` password entry; use manual Google click or switch to `Login with email` for full-auto.
