# yt-dlp Real Provider Abstraction (Termux / Next.js)

Validated 2026-08-23 on Termux Android (arm64) with yt-dlp 2026.06.09 + Next.js 16.3.2.

## When to use

Universal video downloader where `src/lib/providers.ts` must return real direct URLs, not mocked placeholders. User explicitly rejects mock/demo ("jangan demo / bukan mock").

## Provider interface (kept)

```ts
export interface Provider {
  id: Platform;
  getInfo(url: string): Promise<VideoInfo>;
  getDownloadUrl(url: string, quality: Quality): Promise<string>;
}
```

## Real implementation (Node execFile)

```ts
import { execFile } from "child_process";
import { promisify } from "util";
const execFileAsync = promisify(execFile);

async function ytdlpJson(url: string) {
  const args = ["--js-runtimes","node","--no-playlist","--skip-download","--dump-json","--no-warnings", url];
  const { stdout } = await execFileAsync("yt-dlp", args, { timeout: 25000, maxBuffer: 12*1024*1024 });
  const line = stdout.trim().split("\n").find(l => l.trim().startsWith("{")) || stdout;
  return JSON.parse(line);
}
async function ytdlpGetUrl(url: string, format: string) {
  const args = ["--js-runtimes","node","--no-playlist","--get-url","--no-warnings","-f", format, url];
  const { stdout } = await execFileAsync("yt-dlp", args, { timeout: 25000 });
  return stdout.trim().split("\n").filter(Boolean)[0];
}
function formatForQuality(q: Quality) {
  switch(q){
    case "1080p": return "bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b[height<=1080] / bv*+ba/b";
    case "720p":  return "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720] / bv*+ba/b";
    case "360p":  return "bv*[height<=360][ext=mp4]+ba[ext=m4a]/b[height<=360] / bv*+ba/b";
    case "audio": return "ba/bestaudio";
  }
}
```

### Why `--js-runtimes node`

Without it yt-dlp warns `No supported JavaScript runtime could be found` and some YouTube formats are missing. On Termux `node` is already present — no need to install `deno`.

## API routes

- `POST /api/info` → `getInfo()` → return `{title, thumbnail, duration, author, qualities}` (strip `rawFormats` to keep payload small). On yt-dlp error, return `String(e.stderr||e.message).slice(0,900)` with 500 so frontend can show it.
- `POST /api/download` → `getDownloadUrl()` → `{downloadUrl}` (direct googlevideo URL, expires quickly).
- `GET /api/download?url=&quality=` → fetch `directUrl` then pipe as attachment:

```ts
const upstream = await fetch(direct);
headers.set("Content-Type", upstream.headers.get("content-type")||"video/mp4");
headers.set("Content-Disposition", `attachment; filename="savevid-${platform}-${quality}.mp4"`);
return new NextResponse(upstream.body as any, { headers });
```

Frontend `Downloader.tsx` triggers download via hidden anchor to `GET` endpoint, not via `alert()` mock.

## Verification

```bash
curl -s -X POST http://127.0.0.1:3001/api/info -H "Content-Type: application/json" \
  -d '{"url":"https://www.youtube.com/watch?v=jNQXAC9IVRw"}' | jq .title
# → "Me at the zoo" (real)

curl -s -I "http://127.0.0.1:3001/api/download?url=https%3A%2F%2Fwww.youtube.com%2Fwatch%3Fv%3DjNQXAC9IVRw&quality=360p" | grep content-disposition
# → attachment; filename="savevid-youtube-360p.mp4"
```

## Pitfalls

- yt-dlp TikTok/Facebook can fail if extractor is outdated — `pip install -U yt-dlp` and retry before claiming platform unsupported.
- Direct URLs expire (≈6h) — do not cache them; always re-resolve per download click.
- Rate limit `src/lib/rate-limit.ts` (10/min/IP) still applies; include `X-RateLimit-Remaining` header.
