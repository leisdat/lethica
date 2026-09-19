---
name: internal-api-discovery
description: "Use when a site's AJAX bypasses UI gates (premium, limits)."
---

# Internal API Discovery — bypass frontend gates via site's own AJAX

Many sites gate their HTML pages (premium lock, daily limit, guest limit) but leave their
internal AJAX endpoints **ungated** — the same endpoints the frontend JS calls. Finding
and calling them directly can bypass the site's own restrictions.

## Workflow

### 1. Fetch the authenticated page

Get the detail/watch page **while logged in** (or at least with a session cookie).
The internal API tokens are almost always embedded in the page HTML.

```bash
curl -sL "https://situs.co/nonton/{slug}/" -b "PHPSESSID=...; login=..." > page.html
```

### 2. Extract inline JS variables

Inline `<script>` blocks (not external `.js` files) contain site-specific variables:

```bash
node -e "
const h = require('fs').readFileSync('page.html','utf8');
const scripts = [...h.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]);
scripts.forEach((s,i) => {
  if (/token|mId|api|ajax|episode|stream|csrf|id|secret/i.test(s))
    console.log('script #'+i+':', s.slice(0,500));
});
"
```

Look for:
- `var token = "..."` — myapi/ajax token
- `var mId = 1234` — media/content ID
- `var link = "..."` — slug/path
- `var USER_REF_CODE = "..."` — referral code

### 3. Find AJAX calls in the same page

Grep for `$.ajax`, `fetch(`, `.post(`, `.get(` that reference internal paths:

```bash
node -e "
const h = require('fs').readFileSync('page.html','utf8');
const calls = [...h.matchAll(/((?:ajax|post|fetch)\s*\(\s*[\"']?)([^'\")}\s]+(?:myapi|ajax|api|internal)[^'\")}\s]*)/gi)];
for (const c of calls) console.log(c[2]);
"
```

### 4. Test the endpoint

```bash
curl -s -m 20 "https://situs.co/myapi/episode_detail.php" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=$TOKEN&id=$MID&episode=$N"
```

### 5. Follow the chain to the CDN

The JSON response may contain:
- `streaming_premium` or similar — URL to CDN gateway
- `streaming` — file ID
- `is_any_cdn` / `is_any_rtmp` — flags

The CDN gateway often redirects to a direct MP4/HLS URL with **no authentication**:

```bash
curl -sIL -m 20 "http://cdn-gateway.com/go/files/{fid}"
# → 302 → http://cdn-server.com/files/<hash>.mp4 (video/mp4, 200-400MB)
```

### 6. Verify stream support

```bash
curl -s -r 0-1023 -o /dev/null -w "HTTP %{http_code} | type=%{content_type} | bytes=%{size_download}\n" \
  "$FINAL_MP4_URL"
# HTTP 206 = partial content / Range = seekable, playable
```

## Why this works

1. **Frontend gates are separate from data APIs** — the HTML page checks premium/daily-limit,
   but the AJAX endpoint the SAME page calls may skip those checks (designed for internal use).
2. **Tokens are scoped per-page** — the `token` variable in inline JS is for session validation,
   NOT for authorization. It authenticates the request, it doesn't check permissions.
3. **CDN URLs are unsigned** — the CDN gateway (`admin.drakor.la/go/files/{fid}`) redirects to
   a direct CDN URL with no auth, no cookie, no referer check. Once you have the file ID, you
   have the video.

## Pitfalls

### Gate detection order matters

When testing the watch page (fallback method), a page can contain **multiple gate messages**
at once:
1. Premium early-access: `member gratis baru bisa akses pada ...`
2. Guest limit: `hanya bisa streaming 1x|1x dalam sehari`
3. Daily limit: `batas maksimal download harian ...`

Check them **in this order** — premium-early first, then guest-limit, then daily-limit.
If you check guest-limit first, premium episodes get mis-classified as guest-limited.

### Re-throw error gates

If you call the internal API endpoint from within a try/catch loop (e.g., iterating
stream methods), make sure to **re-throw** error gates:
```js
if (e.message.startsWith("PREMIUM_EARLY:")) throw e;
if (e.message.startsWith("DAILY_LIMIT:")) throw e;
```
Otherwise the caller gets `data:[]` (empty array) which is misleading — it looks like
the episode doesn't exist, when really it's gated.

### Attack vectors that DON'T work

- **Rotating device_id UUID** — server tracks by **IP**, not cookie. Changing device_id
doesn't help (wasted effort).
- **JWT/URL token replay** — file IDs are **per-episode unique**. A token from EP1
can't unlock EP6.

## Integration pattern (extension)

In a scraper/extension:
1. Try myapi/internal endpoint **first** (bypass total — no gate, no cookie, no limit)
2. Only fall back to watch-page scraping if myapi fails
3. Keep gate detection (premium-early, guest-limit, daily-limit) on the fallback route

```js
// Priority: myapi → watch-page
// 1. Try internal API
const json = await internalApiCall(slug, epNum);
if (json.streaming_premium) {
  streams.push({ url: json.streaming_premium, type: 'mp4' });
  return streams;
}
// 2. Fallback to watch-page scraping
const html = await fetchHtml(watchUrl);
// ... existing gate detection + iframe parsing
```

## Reference: drakorid case study

See `references/drakorid-myapi-bypass.md` for the full session transcript and
reproducible curl commands from the 2026-09-02 bypass.
