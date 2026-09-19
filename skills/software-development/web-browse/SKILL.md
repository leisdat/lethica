---
name: web-browse
description: Use for authenticated web access, logins, or cookie auth.
version: 1.0.0
author: letticha
license: MIT
metadata:
  hermes:
    tags: [browser, cookies, auth, web, curl, termux]
    related_skills: []
---

# Web Browse — Authenticated Web Access for AI Agents

Hermes built-in `web_extract`/`web_search` don't handle cookies, sessions, or login flows. This skill bridges that gap with **cookie-based browsing via curl** and a **Node.js cookie manager** — works entirely on Termux without Chrome/Puppeteer/Docker.

## When to Use

- User asks to access a page behind login (dashboard, API console, private repo, etc.)
- User needs to automate form login and keep session alive across requests
- User provides login credentials and wants the agent to fetch authenticated data

## How It Works

Cookies stored in `~/.web-cookies/<site-name>.txt` (Netscape format, compatible with curl + Node.js).

**Login flow:** curl POST form → save cookies → reuse for all subsequent requests.  
**Session check:** if a cookie file exists, always use `-b` flag.  
**Session expiry:** on 401/302 to login page, re-login.

---

## Quick Commands

### 1. Login (form-based)
```bash
curl -s -c ~/.web-cookies/site.txt \
  -d "username=USER&password=PASS" \
  https://example.com/login
```

### 2. Authenticated GET (reuse cookies)
```bash
curl -s -b ~/.web-cookies/site.txt \
  https://example.com/dashboard
```

### 3. Authenticated POST (form submit)
```bash
curl -s -b ~/.web-cookies/site.txt \
  -d "action=delete&id=123" \
  https://example.com/api/action
```

### 4. Extract page text (like web_extract)
```bash
curl -s -b ~/.web-cookies/site.txt \
  https://example.com/page | python3 -c "
import sys, re, html
text = sys.stdin.read()
text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.S)
text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.S)
text = re.sub(r'<[^>]+>', ' ', text)
text = html.unescape(text)
text = re.sub(r'\s+', ' ', text).strip()
print(text[:5000])
"
```

---

## Script: Cookie Manager (`~/.web-cookies/manage.mjs`)

Node.js script untuk login + authenticated fetch yang lebih robust.

```bash
cd ~/.web-cookies && node manage.mjs login "https://site.com/login" "username=x&password=y" "site"
cd ~/.web-cookies && node manage.mjs fetch "https://site.com/dashboard" "site"
```

Let the agent run this script rather than raw curl for better error handling and session renewal.

### Script source

Save to `~/.web-cookies/manage.mjs`:

```js
#!/usr/bin/env node
import fs from 'fs';
import os from 'os';
import path from 'path';

const COOKIE_DIR = path.join(os.homedir(), '.web-cookies');
if (!fs.existsSync(COOKIE_DIR)) fs.mkdirSync(COOKIE_DIR, { recursive: true });

const cmd = process.argv[2];
const url = process.argv[3];
const site = process.argv[5] || new URL(url).hostname.replace(/^www\./, '');
const jarFile = path.join(COOKIE_DIR, `${site}.txt`);

if (cmd === 'login') {
  const body = process.argv[4] || '';
  const r = await fetch(url, { method:'POST',
    headers:{'Content-Type':'application/x-www-form-urlencoded'},
    body, redirect:'manual'
  });
  const setCookies = r.headers.get('set-cookie') || '';
  fs.writeFileSync(jarFile, setCookies, 'utf8');
  console.log('Login:', r.ok ? 'OK' : `FAIL (${r.status})`);
  if (!r.ok) { console.error(await r.text().catch(()=>'')); process.exit(1); }
  console.log('Cookies saved to', jarFile);

} else if (cmd === 'fetch') {
  let cookie = '';
  try { cookie = fs.readFileSync(jarFile, 'utf8'); } catch {}
  const r = await fetch(url, { headers: { 'Cookie': cookie, 'User-Agent': 'Mozilla/5.0' }});
  if (r.status === 401 || r.status === 302) {
    console.error('Session expired — need re-login');
    process.exit(1);
  }
  const text = await r.text();
  const clean = text.replace(/<script[^>]*>.*?<\/script>/gs, '')
    .replace(/<style[^>]*>.*?<\/style>/gs, '')
    .replace(/<[^>]+>/g, ' ')
    .replace(/&[a-z]+;/g, ' ')
    .replace(/\s+/g, ' ').trim();
  console.log(clean.slice(0, 10000));

} else {
  console.log(`Usage: node manage.mjs login|fetch <url> [body] [site-name]`);
}
```

Save the above to `~/.web-cookies/manage.mjs` (Node 24 fetch built-in, no deps).

---

## Specific Sites

### Simple form login (most PHP/Node sites)
```bash
# First request to get CSRF token, then login
CSRF=$(curl -s -c cookies.txt https://site.com/login | grep -oP 'name="csrf_token" value="\K[^"]+')
curl -s -c cookies.txt -b cookies.txt \
  -d "csrf_token=$CSRF&email=user@x.com&password=pass" \
  https://site.com/login > /dev/null
```

### Google login — ✅ but needs real browser
Google uses OAuth2 + JavaScript + CAPTCHA. Cookie-only login does NOT work. For Google:
- Use OAuth2 device flow (get token, then use `Authorization: Bearer` header)
- Or use saved cookies from a real browser session

### API token auth (simpler alternative)
Many sites offer API tokens that are easier to automate:
```bash
curl -s -H "Authorization: Bearer TOKEN" https://api.example.com/data
```

---

## Limitations (honest)
- ❌ **Google / OAuth / SSO sites** — need a real browser (JavaScript + redirects). Cookie-only can't handle this.
- ❌ **CAPTCHA-protected login** — curl can't solve CAPTCHA.
- ❌ **SPA / JavaScript-rendered pages** — HTML extract will miss dynamic content.
- ✅ **Form-based login** (most admin panels, forums, simple websites) — works perfectly.
- ✅ **API with token/cookie auth** — works.
- ✅ **Session persistence** across multiple Hermes requests — works.

## Pitfalls
- Always use `-c` (write) AND `-b` (read) for the **same** cookie file.
- Check `set-cookie` header for session expiry.
- Some sites require specific `User-Agent` or `Referer` headers.
- CSRF tokens often embedded in HTML; grep before POST.
- Cookie file in Netscape format: `curl -c jar.txt` writes it, `-b jar.txt` reads it.