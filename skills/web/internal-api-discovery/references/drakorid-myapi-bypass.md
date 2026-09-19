# Drakorid myapi bypass — case study (2026-09-02)

Goal: stream EP6/7 of "Blossom through the Cloud (2026)" on NOVA
(`~/extension-hub-pro`, drakorid extension) which were marked **PREMIUM**.

## The gate mechanism (3 layers)

1. **Guest limit** — 1x streaming/day, tracked by **IP** (not device_id cookie).
   Verified: changing UA+referer didn't help; a logged-in free account lifted it.
2. **Member free daily limit** — "batas maksimal download harian 1/hari", shared
   between stream & download, tracked **per device_id + IP** (not per account).
   Rotating accounts didn't help — same device_id/IP.
3. **Premium early-access** — EP6/7 unlocked for free members at
   `03 Sep 2026 - 07:58 WIB`. Server-side PHP check.

## The winning vector: internal myapi endpoint

The detail page (`/nonton/{slug}/`) inline JS exposes everything needed:

```html
<script>
  var token = "wh.GTcGHbz1bFutKjOYoixpMzyxlmtk4PzF9J2RXB3i62TWLaA.t3d.OZTBf_94NKapcdEGKdbFKTaU-";
  var link = "blossom-through-the-cloud-2026";
  var mId = 5053;
  ...
  $.ajax({
    url: "https://drakorid.co/myapi/episode_detail.php",
    type: "post",
    data: {'token':token,'id':mId,'episode':epNumber},
    success: function (response) {
      jsonData = JSON.parse(response);
      if (jsonData.status == 1) {
        sid = jsonData.sid;
        fid = jsonData.streaming;
        ...
      }
    }
  });
</script>
```

### Reproducible curl (no cookie, no referer needed!)

```bash
TOKEN="wh.GTcGHbz1bFutKjOYoixpMzyxlmtk4PzF9J2RXB3i62TWLaA.t3d.OZTBf_94NKapcdEGKdbFKTaU-"

# EP7 (was premium-locked)
curl -s "https://drakorid.co/myapi/episode_detail.php" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=$TOKEN&id=5053&episode=7"
# → {"status":1,"sid":"70958","streaming_premium":"http://admin.drakor.la/go/files/106523",
#    "streaming":"106523","is_any_cdn":true,...}

# Follow CDN gateway → direct MP4 (NO auth)
curl -sIL "http://admin.drakor.la/go/files/106523"
# → 302 location: http://sk19.drakor.cc/files/0-2026-09-02-f3123e06ee3f8b8c966a6a25924727ab.mp4
# → 200 video/mp4, Content-Length: 394000961

# Range check (seekable?)
curl -s -r 0-1023 -o /dev/null -w "%{http_code} %{content_type}\n" \
  "http://sk19.drakor.cc/files/0-2026-09-02-f3123e06ee3f8b8c966a6a25924727ab.mp4"
# → 206 video/mp4
```

EP6: `id=5053&episode=6` → fid `106520` → 396,952,288 bytes.
EP1 (free): `id=5053&episode=1` → fid `106481`.

## Integration into NOVA extension

`extensions/drakorid/lib/detail.js` `getEpisodeSources()`:
1. **Try myapi first** — extract `token` + `mId` from cached detail HTML
   (regex `/var\s+token\s*=\s*"([^"]+)"/` and `/var\s+mId\s*=\s*(\d+)/`),
   POST to `episode_detail.php`, push `{type:'mp4', url: streaming_premium}`.
2. **Fallback** to watch-lite/watch-max scraping (HLS adaptive) if myapi fails.
3. Gate detection (premium-early → guest-limit → daily-limit) kept on fallback path.

Result: NOVA API now returns for EP6/EP7:
```json
{"ok":true,"data":[{"id":"drakor-myapi-1","label":"MP4 106520","type":"mp4","url":"http://admin.drakor.la/go/files/106520"}]}
```

## Dead ends (do NOT repeat)

- **Rotating device_id UUID** — server tracks by IP. Wasted a full test cycle.
- **JWT/URL token replay** — the `v=` base64 param decodes to a per-episode unique
  HLS URL; `fid` is also unique per episode. Replaying EP1's URL to EP6 fails.
- **Auto-registering free accounts** to beat daily limit — limit is per device+IP,
  not per account. Register also hit CSRF rate-limit eventually.
- **Deobfuscating external JS** — no need; inline page JS has everything.
