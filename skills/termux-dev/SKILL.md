---
name: termux-dev
description: Use when building or testing web/Node projects in Termux.
version: 1.0.0
---

# Developing & Testing on-device in Termux (Android)

Projects often live under `~/storage/downloads/<project>` (shared storage), which maps to
`/storage/emulated/0/Download/<project>`. This causes several Android-specific quirks.

## Termux shell & terminal setup (zsh, p10k, productivity tools)
- See [references/termux-shell-setup.md](references/termux-shell-setup.md) — full "make
  Termux enak" recipe: zsh + Oh My Zsh + powerlevel10k + fzf/zoxide/eza/bat, extra-keys row
  & `termux.properties` UI tweaks, and three durable gotchas: **gitstatusd can't run on
  Termux** (bionic vs glibc → set `POWERLEVEL9K_DISABLE_GITSTATUS=true`), p10k's
  gitstatus `./install` fails because `/tmp` is unwritable (mktemp trap), and modern
  Termux `chsh` stores the login shell as a `~/.termux/shell` symlink (no `/etc/passwd`).
  Apply properties with `termux-reload-settings`.

## Path quirks (shared storage)
- Node's loader sometimes resolves relative args through the REAL Android path
  (`/storage/emulated/0/...`), which can fail where the Termux bind-mount path works.
  Workaround: pass explicit file paths, not directories.
  - `node --test test/` → may fail with `Cannot find module '/storage/emulated/0/Download/<proj>/test'`
  - `node --test test/api.test.js` (direct file) → works
- Avoid `search_files` over projects with `node_modules` on shared storage — results flood
  with dependency files and get truncated uselessly. Use `terminal` with `ls` on the
  project root instead.

## Previewing a web page on the phone's own browser
- Serve with `python3 -m http.server 8080 --bind 127.0.0.1` (background=true) from the
  directory containing the HTML, then tell the user to open `127.0.0.1:8080/<file>.html`
  in Chrome. Node dev servers on localhost work the same way.
- For Node servers: run with terminal background=true (foreground calls that look like
  long-lived servers are rejected), then verify with `curl http://localhost:<port>/health`
  in a separate call.

## Browser cache busting (Chrome on Android is aggressive)
- Chrome Android serves stale JS/CSS with 304 Not Modified and the user sees an old UI.
- Fix: version query strings on asset tags (`app.js?v=2.2.0`) and bump the version on
  every frontend change. Have the user pull-to-refresh after a bump.
- A plain "Memuat…" text placeholder reads as "stuck" to users on slow connections.
  Prefer animated skeleton placeholders plus a "slow connection" note after ~3s.

## Verification without a browser tool
- `node --check file.js` validates syntax of extracted JS (extract `<script>` blocks with
  a short python regex when checking single-file HTML apps). Note `/tmp` may not exist;
  write scratch files under the home directory.
- `curl` endpoints and inspect JSON shape before claiming a UI works.
- You usually cannot screenshot the user's browser — ask for a screenshot when debugging
  "it doesn't work" reports; the described symptom often differs from the real state.

## User sends a screenshot but vision tool can't see it
- See [references/vision-screenshot-recovery.md](references/vision-screenshot-recovery.md) —
  Hermes vision tool runs in a sandbox WITHOUT access to Termux's local fs and fails on
  progressive JPEGs. Recover via `tesseract` OCR + `ffmpeg`/PIL re-encode; corroborate with
  served-file `curl` byte-size checks (ground truth = code, not OCR).

## Single-file HTML app pattern (user's preferred deliverable)
For games, comic readers, docs sites, and similar the user is happiest with one
self-contained HTML file (embedded CSS/JS, CDN fonts OK, no build step) copied to both
`~/<Name>.html` and `~/storage/downloads/<Name>.html` so they can open it directly from
Downloads as well as via a local server. Validate with the JS-extraction check above,
then serve locally for preview.

## JAR/APK inspection

- See [references/apktool-setup.md](references/apktool-setup.md) for fixing `apktool: can't find apktool.jar` errors — symbolic link solution, verification steps, and why TERMUX-specific paths cause this issue.

- `unzip -l file.jar` + `unzip -p file.jar META-INF/MANIFEST.MF` reveal MIDlet class, vendor, version instantly. Assets are plain PNG trees; `.class` code is obfuscated single-letter names. Good first step for triaging old game jars.
- `unzip -l file.jar` + `unzip -p file.jar META-INF/MANIFEST.MF` reveal MIDlet class, vendor, version instantly. Assets are plain PNG trees; `.class` code is obfuscated single-letter names. Good first step for triaging old game jars.
- For Android APK install failures, see [references/android-apk-install-debug.md](references/android-apk-install-debug.md) — signature check → package identity → device compatibility → existing-package conflict diagnostic.
- For building a FULL multi-module Gradle app (no NDK): [references/android-apk-build-full.md](references/android-apk-build-full.md) — prebuilt-.so-from-official-APK + JNI symbol check, `aapt2 --rename-manifest-package` to coexist while keeping JNI packages, manual Maven nearest-wins dep resolution, multi-module R, minSdk/desugaring, resource-conflict scan.

## Git workflow on-device — check `git rev-parse --show-toplevel` FIRST
- A stray `git init` once ran inside `$HOME` here, so a repo rooted at HOME silently
  tracked 2000+ files: `.bash_history`, `.npm/_cacache`, `.gitconfig` — with a remote
  pointing at an unrelated GitHub repo. Symptoms: `git status` from a project dir shows
  `../` paths; project "has a commit" that is really a HOME snapshot ("Initial deploy").
- Before committing project work: verify `git rev-parse --show-toplevel` is INSIDE the
  project; if it's HOME, `git init -b main` in the project root to shadow the outer repo,
  write a `.gitignore` covering `node_modules/`, runtime state dirs (`.data/`, `repo/`),
  and keyring/secrets (`keys/`, `*.pem`), then commit in atomic layers (chore init →
  core → fixes → UI → test scripts). Never "fix" the HOME repo by deleting — it may be
  the user's own; flag it instead.
- Verify what got tracked: `git ls-files | grep -iE '\.pem|\.key|secret|\.env|token'`
  must be empty before calling a commit safe.

## Scraper/API audit & repair
- See [references/scraper-audit-repair.md](references/scraper-audit-repair.md) —
  probe-per-capability audit script, read-the-real-error-body, selector repair against
  saved live HTML (wrong page / tabs-vs-panels / locale drift), full-chain
  detail→episodes→sources verification, and when a worker-pool fix needs no restart.

## PM2 Node backend audit chain
- See [references/pm2-backend-audit-chain.md](references/pm2-backend-audit-chain.md) —
  NOVA case 2026-09-02: 12 bugs surfaced one at a time. Order matters: cached log
  noise (flush first) → frontend/backend endpoint contract → method missing → import
  destructuring → worker module path gotcha → `pm2 flush` discipline. Same chain
  applies to SPECTER (Python) and 9Router/Routerku (Node single-process).

## Dual-theme (dark+light) CSS systems
- See [references/theme-token-discipline.md](references/theme-token-discipline.md) —
  why inverted light themes read "polos" (themed text on hardcoded dark panels, neon
  glow invisible on white, dark shadows on paper), the `color-mix(var(--primary))`
  adaptive-token pattern, light-theme shadow/identity recipe, and WCAG AA contrast
  steps for brand colors on white.

## PM2 & long-running Node daemons on Termux
- See [references/pm2-termux-process-management.md](references/pm2-termux-process-management.md) —
  start/user services under `pm2 start` + `pm2 save` + `pm2 resurrect` at boot via
  Termux:Boot (NOT `pm2 startup`, which fails on Termux); crash-loop diagnosis where an
  orphaned non-PM2 `node` still holds the port (kill -9 the orphan, restart PM2, confirm ↺
  stops climbing); netstat/lsof/ss port checks LIE on Termux — verify with curl instead;
  wrangler can't install on android-arm64 (workerd unsupported) → plan manual REST deploy.

## "Coba ini bisa gk di HP?" — tool feasibility
- See [references/tool-feasibility-termux.md](references/tool-feasibility-termux.md) —
  when the user links a GitHub repo asking if a tool can run on Termux: pull README
  prerequisites, check Docker/glibc/X11 blockers, weigh available RAM, and recommend
  the lightest working alternative. Includes the ClawSec skill-suite evaluation notes.

## Updating Hermes itself on Termux — build failures & fixes
- See [references/hermes-update-termux.md](references/hermes-update-termux.md) —
  three distinct build failures when `hermes update` compiles Rust/C deps from
  source on Termux: (1) maturin needs `ANDROID_API_LEVEL=30` (NOT 33 — platform
  tag mismatch: android_33 wheel rejected by uv), (2) corrupted pydantic-core
  build cache → `rm -rf ~/.cache/uv/sdists-v9/pypi/pydantic-core*`, (3) git
  autostash conflict on `agent/prompt_builder.py` (keep both sides). Plus
  `HERMES_REDTEAM` env var must be real (not just text in SOUL.md), config.yaml
  edits require shell bypass (patch tool refuses), and post-update cleanup.

## Networking & health on Android 13 (netlink blocked → curl-only verification)
- See [references/termux-networking-and-health.md](references/termux-networking-and-health.md) — `ip/ifconfig/ss/netstat/dumpsys wifi` all Permission denied; LAN IP via Node UDP `connect('8.8.8.8:80')` trick (verified `10.65.119.55`); curl 307/dashboard = healthy (don't trust ss); 9Router `--log` re-verified (without → 000); routerku auto-reload DB in 2s + watchdog.

## Deploying Node apps from Termux to PaaS (GitHub → Vercel/Render)
- See [references/deploy-from-termux.md](references/deploy-from-termux.md) — fine-grained
  GitHub PAT via curl (gh auth rejects it), token-in-URL git push (token never persisted),
  Vercel CLI device flow on Termux, vercel.json `headers[].source` pattern pitfall
  (no `?` mid-pattern — use `/js/:path*` per dir), static-UI + backend split with API
  rewrites, Railway CLI unsupported on android-arm64 → Render Blueprint (`render.yaml` +
  `/api/health`) as the fallback.

## Phone operation with permission gate (Termux:API)
- Proven pattern in `~/agent/skills/user/android_device.py` v0.8: SAFE actions
  (probe/battery/volume/audio_info/tts_engines/camera_info/sensor_list) run free;
  everything privacy- or system-changing returns `{policy_deny, deny_kind:"phone"}`
  unless `task.grants` holds `{type:"phone", pattern}` = action, comma list, or
  `"all"`. Bot surfaces `/allow <id> phone "<aksi>|all"` + `/deny`.
- Detail: [references/phone-permission-gate.md](references/phone-permission-gate.md) —
  tier table, grant-check snippet, correct CLI flags (location/sensor/mic/camera),
  companion-app-missing detection, and what works without the app.

## Exposing a local server to other networks (TV on other WiFi, public URL)
- See [references/public-tunnel-termux.md](references/public-tunnel-termux.md) — netlink is
  blocked → LAN IP via Node UDP `connect()` trick; localhost.run SSH tunnel (`nokey@localhost.run`,
  serveo times out) + auto-reconnect loop under PM2 (don't grep-pipe the ssh output);
  **cloudflared: `pkg install cloudflared` WORKS, the GitHub prebuilt binary fails**
  (`unexpected e_type: 2`); stable URL = Cloudflare named tunnel on user's domain (NS switch);
  Render free tier requires a payment card.
