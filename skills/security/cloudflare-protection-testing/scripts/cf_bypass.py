#!/usr/bin/env python3
"""
Cloudflare Anti-Bot Bypass Toolkit — untuk uji keamanan situs SENDIRI.
========================================================================
Mode:
  1. impersonate  — curl_cffi, TLS fingerprint browser asli (Chrome/Safari/Firefox)
  2. cloudscraper — solver otomatis untuk challenge ringan
  3. curl         — curl biasa + header browser lengkap + HTTP/2

Deteksi hasil:
  - BLOCKED  : "Just a moment", cf-chl, challenge-platform, Turnstile, 403
  - OK       : konten halaman asli dimuat

Pemakaian:
  python3 cf_bypass.py <url> [--mode all|impersonate|cloudscraper|curl]
"""
import argparse
import re
import sys
import time

CHALLENGE_MARKERS = [
    # marker kuat — hanya muncul di halaman challenge beneran
    "cf-chl-", "challenge-platform", "cf_chl_opt", "cf-chl-running",
    "turnstile", "cf-please-wait", "just a moment", "enable javascript and cookies",
]
# marker lemah — bisa muncul di konten normal (mis. dokumentasi yang nyebut "challenge")
# → dipakai hanya kalau status 403/429 (bukan 200)
WEAK_MARKERS = ["attention required", "verify you are human", "cf-error", "challenge"]

def classify(body, status):
    """Klasifikasi hasil: OK / CHALLENGE / BLOCKED / ERROR"""
    low = (body or "").lower()
    if status == 403 and "cloudflare" in low:
        return "BLOCKED (CF 403)"
    if status in (403, 429) and any(m in low for m in CHALLENGE_MARKERS + WEAK_MARKERS):
        return "CHALLENGE"
    # status 200 + marker kuat → challenge (masih valid walau status 200)
    if any(m in low for m in CHALLENGE_MARKERS):
        return "CHALLENGE"
    if status == 200 and len(body or "") > 1000:
        return "OK"
    if status == 200:
        return "SUSPECT (200 tapi pendek)"
    return f"HTTP {status}"

def mode_impersonate(url, attempts=None):
    from curl_cffi import requests as creq
    attempts = attempts or ["chrome", "safari", "firefox", "edge", "chrome110"]
    out = []
    for imp in attempts:
        try:
            t0 = time.time()
            r = creq.get(url, impersonate=imp, timeout=25,
                         headers={"Accept-Language": "en-US,en;q=0.9"})
            dt = (time.time() - t0) * 1000
            verdict = classify(r.text, r.status_code)
            out.append((imp, r.status_code, verdict, round(dt),
                        len(r.content), r.headers.get("server", "")))
            if verdict.startswith("OK"):
                return out  # berhenti di yang berhasil
        except Exception as e:
            out.append((imp, 0, f"ERR {str(e)[:60]}", 0, 0, ""))
    return out

def mode_cloudscraper(url):
    import cloudscraper
    out = []
    scraper = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "android", "desktop": False}
    )
    for delay in (0, 3, 6):
        try:
            t0 = time.time()
            r = scraper.get(url, timeout=30)
            dt = (time.time() - t0) * 1000
            verdict = classify(r.text, r.status_code)
            out.append((f"cloudscraper(delay={delay})", r.status_code, verdict,
                        round(dt), len(r.content), r.headers.get("server", "")))
            if verdict.startswith("OK"):
                return out
        except Exception as e:
            out.append((f"cloudscraper(delay={delay})", 0, f"ERR {str(e)[:60]}", 0, 0, ""))
        time.sleep(delay)
    return out

def mode_curl(url):
    import subprocess
    out = []
    ua = ("Mozilla/5.0 (Linux; Android 13; 2201117PG) AppleWebKit/537.36 "
          "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
    cmd = [
        "curl", "-s", "-o", "-", "-w", "\n__META__%{http_code}",
        "--http2", "-L", "--max-time", "25",
        "-H", f"User-Agent: {ua}",
        "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "-H", "Accept-Language: en-US,en;q=0.9",
        "-H", "Sec-Fetch-Dest: document",
        "-H", "Sec-Fetch-Mode: navigate",
        "-H", "Sec-Fetch-Site: none",
        "-H", "Upgrade-Insecure-Requests: 1",
        url,
    ]
    try:
        t0 = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        dt = (time.time() - t0) * 1000
        body = p.stdout or ""
        if "__META__" in body:
            body, _, meta = body.rpartition("__META__")
            status = int(meta.strip() or "0")
        else:
            status = 0
        verdict = classify(body, status)
        out.append(("curl+http2+browser-UA", status, verdict, round(dt), len(body), ""))
    except Exception as e:
        out.append(("curl", 0, f"ERR {str(e)[:60]}", 0, 0, ""))
    return out

def banner():
    print("=" * 72)
    print("  CLOUDFLARE ANTI-BOT BYPASS TOOLKIT — uji keamanan situs SENDIRI")
    print("=" * 72)

def report(url, mode, rows):
    print(f"\n  [mode: {mode}] {url}")
    for imp, st, verdict, ms, size, server in rows:
        icon = {"OK": "✅", "CHALLENGE": "⚠️", "BLOCKED": "🛑"}.get(
            verdict.split("(")[0], "❌")
        print(f"    {icon} {imp:<28} {st:<5} {verdict:<28} {ms:>6} ms  {size:>7} B  {server}")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--mode", default="all",
                    choices=["all", "impersonate", "cloudscraper", "curl"])
    args = ap.parse_args()

    banner()
    print(f"  Target: {args.url}")
    print(f"  Mode:   {args.mode}")
    print("-" * 72)

    if args.mode in ("all", "impersonate"):
        rows = mode_impersonate(args.url)
        report(args.url, "impersonate", rows)
    if args.mode in ("all", "cloudscraper"):
        rows = mode_cloudscraper(args.url)
        report(args.url, "cloudscraper", rows)
    if args.mode in ("all", "curl"):
        rows = mode_curl(args.url)
        report(args.url, "curl", rows)

    print("\n" + "=" * 72)
    print("  CATATAN:")
    print("  • Kalau semua CHALLENGE → kena Managed Challenge / Turnstile interaktif.")
    print("    Butuh browser sungguhan (flaresolverr) — tidak feasible di Termux.")
    print("  • Kalau ada yang OK → TLS fingerprint/header kamu gak kena deteksi bot.")
    print("  • Ini UNTUK SITUS SENDIRI — validasi hardening, bukan scraping pihak ketiga.")
    print("=" * 72)

if __name__ == "__main__":
    main()