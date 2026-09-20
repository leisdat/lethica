# core/tools_net.py — v3.7.2 Lethica tools: HTTP / web search / browser (split dari tools.py).
# Browser-impersonating HTTP + search-engine scrape + cookie-jar browse.
import os
import re
import json
import time
import base64
import urllib.request
import urllib.error
import urllib.parse

from core import config, cache

# v2.9.1 HTTP stack: curl_cffi browser impersonation (TLS/JA3 fingerprint).
try:
    from curl_cffi import requests as _curl
    _HAVE_CURL = True
except Exception:
    _curl = None
    _HAVE_CURL = False

SEARCH_UA = "Mozilla/5.0 (Linux; Android 13; Redmi Note 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"


def _curl_request(url, method="GET", headers=None, data=None, timeout=30, impersonate="chrome"):
    """Browser-impersonating HTTP. Return (status, final_url, text, headers, cookies). Raise on fail."""
    s = _curl.Session(impersonate=impersonate)
    r = s.request(method=method.upper(), url=url, headers=headers or {}, data=data,
                  timeout=timeout, allow_redirects=True)
    try:
        cookies = dict(r.cookies)
    except Exception:
        cookies = {}
    return r.status_code, str(r.url), r.text, r.headers, cookies


def _fetch(url, timeout=20):
    """GET URL → text. Raise kalau gagal (caller yang handle)."""
    hdrs = {"User-Agent": SEARCH_UA, "Accept-Language": "en-US,en;q=0.9"}
    if _HAVE_CURL:
        try:
            return _curl_request(url, "GET", hdrs, None, timeout)[2]
        except Exception:
            pass
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _strip_html(s):
    return re.sub(r"<[^>]+>", "", s).strip()


def _decode_bing_redirect(url):
    """bing.com/ck/a redirect → URL asli (base64url di param u=a1)."""
    if "bing.com/ck/a" not in url:
        return url
    um = re.search(r"[?&]u=a1([^&]+)", url)
    if not um:
        return url
    try:
        tok = um.group(1).replace("-", "+").replace("_", "/")
        tok += "=" * (-len(tok) % 4)
        dec = base64.b64decode(tok).decode("utf-8", errors="replace")
        if dec.startswith("http"):
            return dec
    except Exception:
        pass
    return url


def _search_bing(query, limit):
    """Parse hasil Bing. Return list [{title,url,snippet}] — raise kalau fetch gagal."""
    bp = _fetch(f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={limit+5}")
    results = []
    for c in re.split(r'<li class="b_algo"', bp)[1:]:
        h2 = (re.search(r'<a[^>]*href="(http[^"]+)"[^>]*>\s*<h2[^>]*>(.*?)</h2>', c[:3000], re.DOTALL)
              or re.search(r'<h2[^>]*>\s*<a[^>]*href="(http[^"]+)"[^>]*>(.*?)</a>', c[:3000], re.DOTALL))
        if not h2:
            continue
        url = _decode_bing_redirect(h2.group(1))
        title = _strip_html(h2.group(2))
        snm = re.search(r"<p[^>]*>(.*?)</p>", c, re.DOTALL)
        snippet = _strip_html(snm.group(1))[:200] if snm else ""
        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


def _search_ddg(query, limit):
    """Parse hasil DDG lite. Return list [{title,url,snippet}] — raise kalau fetch gagal."""
    page = _fetch(f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}")
    results = []
    for m in re.finditer(
        r"<a[^>]*?href=['\"](https?://[^'\"]+)['\"][^>]*?class=['\"]result-link['\"][^>]*>(.*?)</a>(.*?)(?=<a[^>]*class=['\"]result-link|\Z)",
        page, re.DOTALL,
    ):
        title = _strip_html(m.group(2))
        url = m.group(1)
        if "duckduckgo.com" in url and "/l/?" in url:
            mm = re.search(r"uddg=([^&]+)", url)
            if mm:
                url = urllib.parse.unquote(mm.group(1))
        snm = re.search(r"class=['\"]result-snippet['\"][^>]*>(.*?)</td>", m.group(3), re.DOTALL)
        snippet = _strip_html(snm.group(1))[:200] if snm else ""
        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


def _search_searx(query, limit):
    """SearXNG public instance scrape. Return list [{title,url,snippet}] — raise kalau gagal."""
    import random
    instances = [
        "https://searx.be", "https://search.brave4u.com", "https://search.inetol.net",
        "https://priv.au", "https://baresearch.org", "https://searx.work",
    ]
    inst = random.choice(instances)
    page = _fetch(f"{inst}/search?q={urllib.parse.quote(query)}&format=json", timeout=15)
    try:
        data = json.loads(page)
        results = []
        for r in data.get("results", [])[:limit]:
            url = r.get("url")
            if url and url.startswith("http"):
                results.append({
                    "title": _strip_html(r.get("title", "")) or url,
                    "url": url,
                    "snippet": _strip_html(r.get("content", ""))[:200],
                })
            if len(results) >= limit:
                break
        return results
    except Exception:
        return []


def _search_google_scrape(query, limit):
    """Google scrape via lite endpoint. Return list — raise kalau gagal."""
    page = _fetch(f"https://www.google.com/search?q={urllib.parse.quote(query)}&num={limit+5}", timeout=15)
    results = []
    for m in re.finditer(r'<a href="(https?://[^"]+)"[^>]*><h3[^>]*>(.*?)</h3>', page, re.DOTALL):
        url = m.group(1)
        if "google" in url or "webcache" in url:
            continue
        title = _strip_html(m.group(2))
        snm = re.search(r'<div[^>]*class="[^"]*BNeawe[^"]*"[^>]*>(.*?)</div>', m.group(0), re.DOTALL)
        snippet = _strip_html(snm.group(1))[:200] if snm else ""
        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


def _with_retry(fn, max_attempts=2, base_delay=1.5):
    """Retry fn() dengan exponential backoff. Return list atau raise attempt terakhir."""
    last = None
    for i in range(max_attempts):
        try:
            r = fn()
            if r:
                return r
        except Exception as ex:
            last = ex
        if i < max_attempts - 1:
            time.sleep(base_delay * (2 ** i))
    if last:
        raise last
    return []


def tool_web_search(query, limit=None):
    """Search via chain: Bing → DDG lite → SearXNG → Google scrape. Zero-dep urllib, retry+backoff. Cache 30m (v2.8.6)."""
    limit = max(1, min(int(limit or config.SEARCH_LIMIT), 10))
    ck = f"search:{urllib.parse.quote(query)}:{limit}"
    cached = cache.get(ck, ttl=1800)
    if cached is not None:
        return cached + "\n(cached 30m)"
    errors = []
    for name, fn in (("bing", lambda: _search_bing(query, limit)),
                     ("ddg", lambda: _search_ddg(query, limit)),
                     ("searx", lambda: _search_searx(query, limit)),
                     ("google", lambda: _search_google_scrape(query, limit))):
        try:
            results = _with_retry(fn)
            if results:
                out = json.dumps(results[:limit], ensure_ascii=False, indent=1)
                cache.put(ck, out, ttl=1800)
                return out
        except Exception as ex:
            errors.append(f"{name}: {ex}")
    return f"Error web_search: semua engine gagal ({' | '.join(errors)})"


BROWSER_COOKIE_JAR = {}  # domain -> {cookie: val}
BROWSER_LAST_URL = [None]


def _browser_headers(domain, extra=None):
    h = {"User-Agent": SEARCH_UA, "Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"}
    if domain in BROWSER_COOKIE_JAR:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in BROWSER_COOKIE_JAR[domain].items())
    if extra:
        try:
            h.update(json.loads(extra) if isinstance(extra, str) else extra)
        except Exception:
            pass
    return h


def _browser_store_cookies(resp, domain):
    # v2.5 fix: setdefault dulu — deletion cookie gak KeyError lagi
    try:
        jar = BROWSER_COOKIE_JAR.setdefault(domain, {})
        for hv in resp.headers.get_all("Set-Cookie") or []:
            part = hv.split(";")[0]
            if "=" in part:
                k, v = part.split("=", 1)
                if v.strip().lower() in ("", "deleted"):
                    jar.pop(k, None)
                else:
                    jar[k] = v
    except Exception:
        pass


def _browser_store_cookies_curl(cookies, domain):
    """Simpan cookies dari curl_cffi response (dict) ke jar manual."""
    try:
        jar = BROWSER_COOKIE_JAR.setdefault(domain, {})
        for k, v in (cookies or {}).items():
            if str(v).strip().lower() in ("", "deleted"):
                jar.pop(k, None)
            else:
                jar[k] = v
    except Exception:
        pass


def tool_browse(url, data=None, method="GET"):
    """Browser session dengan cookie jar persist. GET buka page, POST kirim form/login."""
    if not url or not isinstance(url, str):
        return "Error browse: url required (contoh: <browse url=\"https://...\" /> atau tanpa url untuk reload last)."
    if not url.startswith(("http://", "https://")):
        return f"Error browse: invalid url '{url}' (butuh http/https)."
    url = url.replace("\\\"", "\"")
    method = (method or "GET").upper()
    # v2.8: cache GET browse 10 menit (POST gak di-cache — form/login)
    bck = None
    if method == "GET":
        bck = f"browse:{url}"
        bcached = cache.get(bck, ttl=600)
        if bcached is not None:
            return bcached + "\n(cached 10m)"
    if not url.startswith("http") and BROWSER_LAST_URL[0]:
        url = urllib.parse.urljoin(BROWSER_LAST_URL[0], url)
    domain = urllib.parse.urlparse(url).netloc
    try:
        hdrs = _browser_headers(domain)
        body = None
        if data:
            data = data.replace("\\\"", "\"")
            body = data.encode("utf-8")
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
        status = final_url = raw = None
        if _HAVE_CURL:
            try:
                status, final_url, raw, _ch, _cc = _curl_request(url, method, hdrs, body, 30)
                _browser_store_cookies_curl(_cc, domain)
            except Exception:
                status = final_url = raw = None
        if status is None:
            req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=30) as r:
                status = r.status
                final_url = r.geturl()
                raw = r.read().decode("utf-8", errors="replace")
                _browser_store_cookies(r, domain)
        BROWSER_LAST_URL[0] = final_url
        body_m = re.search(r"<body[^>]*>(.*)</body>", raw, re.DOTALL | re.IGNORECASE)
        page = body_m.group(1) if body_m else raw
        page = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", page, flags=re.DOTALL | re.IGNORECASE)
        links = []
        for lm in re.finditer(r'<a[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', page, re.DOTALL):
            txt = re.sub(r"<[^>]+>", "", lm.group(2)).strip()[:80]
            if txt:
                links.append(f"  {lm.group(1)[:120]}  → {txt}")
            if len(links) >= 30:
                break
        text = re.sub(r"<br\s*/?>", "\n", page, flags=re.IGNORECASE)
        text = re.sub(r"</(?:p|div|tr|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text).strip()
        if len(text) > 4000:
            text = text[:4000] + "\n... (truncated)"
        out = f"HTTP {method} {url} → {status} (final: {final_url})\nCookies: {len(BROWSER_COOKIE_JAR.get(domain, {}))} stored\n\n=== PAGE TEXT ===\n{text}"
        if links:
            out += "\n\n=== LINKS ===\n" + "\n".join(links)
        if bck:
            cache.put(bck, out, ttl=600)
        return out
    except urllib.error.HTTPError as he:
        return f"Error browse: HTTP {he.code} {he.reason} on {url}"
    except Exception as ex:
        return f"Error browse: {ex}"
