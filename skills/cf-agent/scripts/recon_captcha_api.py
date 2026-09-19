#!/usr/bin/env python3
"""
Recon script: discover backend host, captcha sitekey, and API enforcement.

Use case: User asks "does this site have captcha that I need to bypass?"
This script answers: where is the backend, what's the captcha provider, and
is the captcha enforced at the API level (not just loaded in JS).

Usage:
    python3 recon_captcha_api.py https://example.com/register

Output: structured report of discovered endpoints, sitekey, and the
captcha enforcement layer (page vs API).

Validated on xkiro.com 2026-09-02: discovered api.xkiro.com backend,
HCAPTCHA_SITEKEY f950cb8c-dc1e-4908-9378-43ead3ccc282, and confirmed
hCaptcha enforced at POST /api/v1/auth/register.
"""
import cloudscraper
import re
import sys
import json


def discover(url):
    scraper = cloudscraper.create_scraper()
    out = {"url": url, "findings": {}}

    # 1. GET page
    r = scraper.get(url, timeout=25)
    out["status"] = r.status_code
    out["page_size"] = len(r.text)

    # 2. CSP → backend hosts
    csp = r.headers.get("content-security-policy", "")
    api_hosts = re.findall(r"https?://([a-zA-Z0-9\-\.]+\.[a-z]{2,})", csp)
    # filter out generic CDNs
    cdns = {"hcaptcha.com", "*.hcaptcha.com", "googletagmanager.com",
            "google-analytics.com", "cloudflareinsights.com",
            "js.stripe.com", "hooks.stripe.com", "gstatic.com"}
    out["findings"]["api_hosts"] = sorted(set(
        h for h in api_hosts
        if h not in cdns and "gstatic" not in h
    ))

    # 3. JS chunks → sitekey + path patterns
    chunks = re.findall(r'src="(/_next/static/chunks/[^"]+)"', r.text)
    if not chunks:
        # Try generic /static/ patterns
        chunks = re.findall(r'src="(/static/[^"]+\.js)"', r.text)
    all_js = "\n".join(
        scraper.get(f'{url.rsplit("/", 1)[0]}{c}').text
        for c in chunks
    ) if chunks else ""

    # Search for hCaptcha sitekey
    sitekey = re.findall(
        r'HCAPTCHA_SITEKEY[:\s]+["\']([a-f0-9-]+)["\']', all_js
    )
    if not sitekey:
        # try data-sitekey in any context
        sitekey = re.findall(r'data-sitekey=["\']([a-f0-9-]+)["\']', r.text)
    out["findings"]["hcaptcha_sitekey"] = sorted(set(sitekey))

    recaptcha = re.findall(
        r'recaptcha[\w]*[\.\s]+(sitekey|SITEKEY)["\']?\s*[:=]\s*["\']([a-zA-Z0-9\-_]+)["\']',
        all_js + r.text
    )
    out["findings"]["recaptcha_sitekey"] = sorted(set(v for _, v in recaptcha))

    turnstile = re.findall(r'(?:turnstile|TURNSTILE)[\.\s]+(SITEKEY|sitekey)["\']?\s*[:=]\s*["\']([a-zA-Z0-9\-_]+)["\']',
                           all_js + r.text)
    out["findings"]["turnstile_sitekey"] = sorted(set(v for _, v in turnstile))

    # 4. API path patterns
    api_paths = re.findall(r'["\'](/(?:api/)?v\d+/[a-z\-/]+)["\']', all_js)
    api_paths += re.findall(r'["\'](/api/[a-z\-/]+)["\']', all_js)
    out["findings"]["api_path_candidates"] = sorted(set(api_paths))[:20]

    # 5. POST probes to confirm enforcement
    if out["findings"]["api_hosts"]:
        backend = out["findings"]["api_hosts"][0]
        backend_url = f"https://{backend}"
        out["findings"]["backend"] = backend_url
        out["findings"]["enforcement_probes"] = []

        for path in ["/api/v1/auth/register", "/api/auth/register",
                     "/api/v1/auth/login", "/api/auth/login"]:
            try:
                pr = scraper.post(
                    f"{backend_url}{path}",
                    json={"email": "test@example.com",
                          "password": "Test1234Pass!@#"},
                    headers={"Origin": url.rsplit("/", 1)[0],
                             "Referer": url,
                             "Content-Type": "application/json"},
                    timeout=15,
                )
                body_snip = pr.text[:300]
                enforced = "captcha" in body_snip.lower() or "Captcha" in body_snip
                out["findings"]["enforcement_probes"].append({
                    "path": path,
                    "status": pr.status_code,
                    "captcha_enforced": enforced,
                    "body_snippet": body_snip,
                })
            except Exception as e:
                out["findings"]["enforcement_probes"].append({
                    "path": path,
                    "error": str(e)[:100],
                })
    return out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    result = discover(sys.argv[1])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
