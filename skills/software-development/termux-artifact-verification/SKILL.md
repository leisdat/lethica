---
name: termux-artifact-verification
description: Use when verifying HTML artifacts or Node tests on Termux.
---

# Verifying & delivering artifacts on Termux (no browser tooling)

## HTML artifact verification without a browser
- Check structure with a Python `html.parser` stack checker: push non-void start tags, pop end tags, report mismatches and unclosed tags at EOF.
- Do NOT use vision_analyze on HTML/SVG files — it needs an SVG rasterizer (cairosvg etc.) that is normally absent; treat that path as unavailable, don't retry it.
- Say explicitly to the user that visual verification was not possible and invite tweak requests.

## Large HTML writes — character-drop artifacts (write_file on big files)
- Writing a large HTML file (40KB+, e.g. a full dashboard redesign) via write_file can silently drop single characters from CSS/JS tokens — producing typos like `colo:` (→`color:`), `overflo` (→`overflow`), `backgrund` (→`background`), `margin-botom`, `spce-between`, `whte-spce`, `border-colr`, `retun`, `joi(`, `s. req` (→`s.req`). The write reports `verified:true` (hash matches what was written), but what was written is corrupt.
- Bulk-fix with a Python `str.replace` pass over a typo→correct map, then RE-SCAN with `re.findall` because the replace pass itself can introduce double-char artifacts (e.g. `overflow` → `overfloww` when the typo `overflo` was already part of a correct `overflow`).
- Verify inline JS syntax by extracting the `<script>` block to a temp `.js` file and running `node --check <file>`. `node --check` catches the syntax errors the character drops introduced (e.g. `Math.round(x)': '–'` → unexpected string). Heredoc `node --check <<'JS'` does NOT work on Termux (ENOENT on the pipe path) — write to a real file first.
- Pitfall: `/tmp` is NOT writable on Termux — writing the temp `.js` to `/tmp/dash.js` fails with `FileNotFoundError: [Errno 2]`. Write temp files under the home dir (`~/dash_check.js`) instead, then `rm` them after the check.
- Pitfall: do NOT trust a single `node --check` pass after the first fix — re-extract and re-check until clean, because each fix pass can introduce its own artifact.

## Delivery location
- Copy the artifact to `~/storage/downloads/` in addition to the home-dir original; the user opens files from Android's Downloads app.

## Node.js on shared storage (/storage/emulated)
- `node --test <dir>` fails with MODULE_NOT_FOUND there: Node resolves the dir to the raw Android path (`/storage/emulated/0/...`) which its loader cannot read.
- Workaround: pass test files directly, e.g. `node --test test/api.test.js`.
- `npm start` / normal scripts work fine from those paths.
- Long-lived servers: run with terminal background=true, then health-check with curl in a separate call.

## Web-extraction fallbacks
- web_extract can fail with backend errors (e.g. missing EXA key). Fallback: GitHub API via curl (`api.github.com/repos/<o>/<r>`) plus raw.githubusercontent.com for README/files — reliable even where page extraction fails.
