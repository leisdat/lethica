# Next.js + yt-dlp on Termux (Android/arm64) — session notes 2026-08-23

## Turbopack unsupported
Error: `Turbopack is not supported on this platform (android/arm64) because native bindings are not available.`
Fix: `npx next build --webpack` and `npx next start --port 3001` . Add `--webpack` to all build/start/dev commands. Don't rely on default turbopack.

## yt-dlp real provider (replaces mock)
- Binary: `/data/data/com.termux/files/usr/bin/yt-dlp` (pip 2026.6.9), `python3 -m yt_dlp` also works.
- Invoke: `execFile("yt-dlp", ["--js-runtimes","node","--no-playlist","--skip-download","--dump-json","--no-warnings", url], {timeout:25000, maxBuffer:12*1024*1024})`
- For direct URL: `["--js-runtimes","node","--no-playlist","--get-url","--no-warnings","-f", format, url]`
- Formats: `bv*[height<=1080][ext=mp4]+ba[ext=m4a]/b` etc. Always fallback to `ba/bestaudio` for audio.

## Streaming endpoint
GET `/api/download?url=&quality=` should `fetch(directUrl, {headers:{"User-Agent":"Mozilla/5.0"}})` and pipe with `Content-Disposition: attachment; filename="savevid-${platform}-${quality}.mp4"` + `Content-Type` from upstream. Return 500 with `String(e.stderr||e.message).slice(0,800)` on failure.

## Kill pattern for Next.js on Termux
`process(action="kill")` only kills Hermes shell. Child `node next-server` survives and keeps port.
Steps: `ps aux | grep next-server` → `kill <pid>` (e.g. 1441 1459) → `sleep 2` → `npx next start --port 3001` (background=true) → verify `curl -m 15 -I http://127.0.0.1:3001/`.

## Frontend txt-bug fix
Blind `<a href="/api/download?url=...">` saves error responses as .txt. Use `fetch(href)` → if `!res.ok` throw `await res.text()` shown as inline `⚠️` error, else `res.blob()` → `URL.createObjectURL` → `<a download="savevid-${platform}-${quality}.mp4">`. Show progress via ReadableStream reader if Content-Length known.
