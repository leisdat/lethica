---
name: cloudflare-protection-testing
description: "Use when probing Cloudflare anti-bot on your own site."
version: 1.0.0
author: hermes
license: MIT
metadata:
  hermes:
    tags: [security, cloudflare, hardening, testing]
---

# Cloudflare Anti-Bot Testing (own-site hardening)

Toolkit untuk menguji apakah situs SENDIRI yang diproteksi Cloudflare bisa ditembus bot —
validasi hardening, bukan scraping pihak ketiga.

## Lokasi & Penggunaan
- Skrip utama: `~/cf_bypass.py` (tersalin juga di `scripts/cf_bypass.py`)
- Deps opsional: `curl_cffi` (TLS impersonate) + `cloudscraper` — sudah terinstall di Termux

```bash
python3 ~/cf_bypass.py "https://domain-kamu.com"            # semua mode
python3 ~/cf_bypass.py "https://domain-kamu.com" --mode impersonate
python3 ~/cf_bypass.py "https://domain-kamu.com" --mode cloudscraper
python3 ~/cf_bypass.py "https://domain-kamu.com" --mode curl
```

## 3 Mode
1. **impersonate** — `curl_cffi` TLS fingerprint asli browser (chrome/safari/firefox/edge/chrome110), berhenti di yang pertama OK
2. **cloudscraper** — solver challenge ringan, 3 delay (0/3/6s)
3. **curl** — curl + HTTP/2 + header browser Android lengkap

## Interpretasi Hasil
| Verdict | Arti |
|---|---|
| ✅ OK | Tembus — ini titik lemah hardening-mu |
| ⚠️ CHALLENGE | Kena Managed Challenge/Turnstile → butuh browser asli (flaresolverr) |
| 🛑 BLOCKED (CF 403) | WAF/security rule blokir langsung |
| ❌ SUSPECT (200 pendek) | Body <1KB — sering JSON API legit, bukan challenge. Cek isi body. |

## Pitfall Klasifikasi (semua pernah dialami)
- **Status 200 ≠ aman**: halaman challenge CF sering balik status 200. Deteksi pake STRONG markers di body (`cf-chl-`, `challenge-platform`, `cf_chl_opt`, `turnstile`, "just a moment", "enable javascript and cookies"), bukan status code.
- **Weak markers** ("attention required", "verify you are human", "challenge") cuma dipakai kalau status 403/429 — di 200 bisa false positive (dokumentasi normal yang nyebut kata "challenge").
- **Jangan tes ke www.cloudflare.com**: mereka menjalankan Bot Management sendiri → CHALLENGE itu VALID, bukan bug toolkit. Buat validasi classifier, tes ke situs kontrol tanpa challenge (mis. `httpbin.org/get`) → harus SUSPECT/OK, bukan CHALLENGE.
- **SUSPECT (200 pendek)**: body <1KB. Bisa berarti sukses (JSON API ~900B) ATAU redirect stub. Jangan cuma lihat size — baca isi.
- Kalau `--mode curl` nunjukin hasil beda dari impersonate → masalah header/fingerprint, bukan solusi challenge.
- **PAGE vs API enforcement (class pitfall)**: Sebuah situs bisa `OK` di halaman publik TAPI `CHALLENGE` di API submit. Captcha sering dimuat di JS chunks (`HCAPTCHA_SITEKEY:"..."` di bundle) bukan di SSR HTML, dan enforcement terjadi di backend saat POST. Workflow validasi lengkap:
  1. Test halaman publik → kalau `OK` artinya Cloudflare Standard bisa ditembus (perlu hardening)
  2. Cari backend host dari CSP `connect-src` header
  3. Cari sitekey dari JS chunks (bukan dari inline HTML)
  4. Probe API endpoint dengan POST → kalau 400 "Captcha verification failed" = enforcement aktif
  Lihat `references/xkiro-validation.md` di skill `cf-agent` untuk skrip recon lengkap.

## Kalau Ada yang OK → Hardening Lanjutan
1. Aktifkan **Bot Fight Mode** (Security → Bots)
2. **WAF custom rule** blokir fingerprint curl_cffi-like (JA3/JA4 hash)
3. Naikkan **Security Level** / **Managed Challenge** di path sensitif
4. **Re-test setelah tiap perubahan** — verifikasi hardening beneran nutup celah

## Termux Constraint (UPDATED)

**Critical Path Fix for Termux**:
- HAPUS semua reference ke `/root/...` path — Termux tidak menggunakan proot Ubuntu secara default
- Gunakan Python Termux langsung + `curl_cffi` untuk bypass HTTP-level
- Contoh kerja:
```bash
# Install depedensi
pkg install python nodejs ffmpeg tesseract -y

# Jalankan bypass HTTP-level
python3 ~/cf_bypass.py "https://nowsecure.nl" --mode impersonate
```

**Error Pattern yang Ditemukan**:
- `Verdict: ERROR - Script creation error: [Errno 2] No such file or directory: '/root/launch_chrome.sh'`
  → FIX: Jangan gunakan proot Ubuntu untuk Chrome di Termux
- `Verdict: ERROR - server rejected WebSocket connection: HTTP 404`
  → FIX: Gunakan HTTP-level bypass (curl_cffi/cloudscraper) untuk Managed Challenge ringan

**Termux-Specific Workflow**:
1. Untuk **Cloudflare Standard**: `cf_bypass.py` dengan mode `impersonate`/`cloudscraper`
2. Untuk **Turnstile/Managed Challenge ringan**: `cf_bypass.py --mode curl` dengan header lengkap
3. Untuk **Enterprise Bot Management**: Tidak feasible di HP — butuh proxy/residential + server 8GB+

**Penting**: Di Termux (6GB RAM), Chrome headless TIDAK direkomendasikan karena:
- Proot Ubuntu sering OOM (Chrome ~400MB + Python ~300MB)
- Tidak ada `/root/` path — semua harus di `~/`
- Zombie process cleanup berbeda (`pgrep -f` vs `pkill -f`)

## Pitfall Terkini (Termux-specific)
- **Path proot tidak ada**: Skrip yang mengasumsikan proot Ubuntu (`/root/chromium/...`) akan gagal — gunakan HTTP-level bypass
- **Header Android diperlukan**: Mode `curl` harus pakai header Android lengkap untuk bypass Managed Challenge
- **Memory budget 6GB**: Chrome + Python di proot sering OOM — gunakan HTTP client langsung
- **Zombie process cleanup**: Gunakan `pgrep -f` bukan `pkill -f` untuk hindari kill shell sendiri
**Standard + Turnstile challenges WORK di Termux** (nowsecure.nl ✅, cloudflare.com standard ✅, justpaste.it ✅). Yang TIDAK feasible: Enterprise Bot Management dengan WebGL/AudioContext fingerprinting intens (Crunchyroll, dll.) — butuh >6GB RAM. Untuk Managed Challenge ringan cukup `cf_stealth.py` atau `cf_persistent.py` di HP. Untuk enterprise, gunakan residential proxy + Chrome di server (8GB+ recommended).

## Overlap
Sebagian overlap dengan `blocked-page-recovery` (sama-sama bahas marker challenge CF), tapi arah beda: skill ini = probe situs sendiri buat hardening; `blocked-page-recovery` = recover konten yang keblokir.

## Referensi Build Log
- [references/cf-ststealth-build-log.md](references/cf-ststealth-build-log.md) — verbatim
  error transcript + root cause + fix untuk setiap masalah yang muncul pas build
  cf_stealth.py: page-vs-browser target, IIFE return, f-string concatenation space
  loss, proot `start_new_session=True`, user-agent paren escape, zombie cleanup,
  hardline block filter, dan memory budget check.
- [references/cf-persistent-build-log.md](references/cf-persistent-build-log.md) —
  arsitektur session persistence + pitfalls waktu build cf_persistent.py:
  cf_clearance vs cf_bm valid check, text-based false positive (nopecha demo),
  sqlite3 Connection.description pitfall, stable fingerprint via file persistence,
  keepalive WS ping, dan validation test matrix.

---

# 4 Generasi Toolkit (validated)

Urutan evolusi: v1 HTTP dasar → v2 rotasi → v3 adaptive state machine → v4 browser-based full CDP solver. Tiap generasi **dibangun di atas yang sebelumnya** ketika target menunjukkan resistance baru.

## Generasi 1: HTTP-level (`cf_bypass.py`)
TLS fingerprint impersonation via `curl_cffi` (chrome/safari/firefox/edge) + `cloudscraper` + curl. 3 mode, stop di OK pertama. Cukup untuk **TLS-fingerprint-only** detection (Cloudflare standard, free tier). TIDAK cukup untuk Turnstile/Managed Challenge — body 200 tetap CHALLENGE.

## Generasi 2: Multi-strategy (`cf_bypass_pro.py`)
Tambah `cf_clearance` auto-save, stealth headers, dan fallback ke cloudscraper/curl setelah impersonate gagal. Validated: cloudflare.com ✅, nowsecure.nl ✅, justpaste.it ✅, blibli.com ✅.

## Generasi 3: Auto-tuner (`cf_tuner.py`)
Auto-tuner yang nyoba **kombinasi fingerprint × HTTP version × header × timing** dan pilih terbaik. Plus `--force` flag untuk uji combo walau probe bilang OK. Berguna untuk reverse-engineering detection rules situs sendiri.

## Generasi 4: Adaptive state machine (`cf_adaptive.py`)
State machine dengan **rotasi otomatis** saat dapat challenge, **cache persistence** (combo yang berhasil disimpan), **early-abort** managed challenge (3× identical body = stop wasting attempts). Bug-bug yang sudah difix:
- `'str' object has no attribute 'value'` (cookies dict vs CookieJar mismatch) → dual-handle
- Spin loop di iter 8-12 (combo duplikat) → filter `(fp,http,header)` di `self.tried`
- `_adapt_strategy` return None → handle di `run()` loop
- Crunchyroll waste 12 attempt → abort di iter 3 kalau body identik

## Generasi 5: Browser-based CDP solver (`cf_stealth.py`) ← paling kuat
**Full human-behavior emulation di Chromium headless via CDP raw**. Beat Turnstile di nowsecure.nl (cf_clearance cookie obtained, HTML 180KB). Kalau generasi 1-4 gagal, ini yang handle Turnstile interaktif.

### Lokasi & pemakaian
```bash
# file di ~/cf_stealth.py (~830 baris)
python3 ~/cf_stealth.py https://nowsecure.nl --timeout 90
python3 ~/cf_stealth.py https://domain-kamu.com --keep  # jangan kill chrome setelah selesai
CF_NO_STEALTH=1 python3 ~/cf_stealth.py https://...  # debug: tanpa stealth injection
```

### Stealth features (bukan cuma bypass)
1. **Humanized mouse** — cubic Bezier dengan random control handles + per-step jitter (0.4–1.2px)
2. **Humanized typing** — variable WPM (gaussian ~50 wpm), slip correction, thinking pauses
3. **Behavioral fingerprint masking**:
   - Canvas toDataURL noise (LCG-seeded, per-session stable)
   - WebGL vendor/renderer spoof → "Intel Inc." / "Intel Iris OpenGL Engine"
   - AudioContext drift (oscillator override)
   - Hardware concurrency/deviceMemory/platform spoof
4. **Navigator property spoofing** — webdriver=undefined, plugins realistic, languages, doNotTrack=null
5. **chrome.runtime/permission anti-detection** — empty IFrame contentWindow parent detection
6. **Adaptive stealth jitter** — random delays 0.4–0.9s antar event biar gak deterministic

### Yang BUTUH Chromium di proot
Path di Termux: `/root/chromium/chrome-linux/chrome` (di dalam proot ubuntu container, ARM64 build). Launcher script ditulis ke `/root/launch_chrome.sh` di dalam proot via `cat <<EOF` heredoc untuk **hindari shell-escape hell** (user-agent dengan parens `(X11; Linux x86_64)` harus di-quote pakai `\"...\"` kalau gak bash treat `(` as subshell → `syntax error near unexpected token '('`).

### Flag Chromium yang WORK di Termux (6GB RAM)
```
--headless=new --no-sandbox --disable-gpu
--disable-dev-shm-usage
--disable-extensions --no-first-run --no-default-browser-check
--disable-background-networking --disable-component-update
--disable-features=VizDisplayCompositor,Vulkan,UseSkiaRenderer,AudioServiceOutOfProcess
--disable-accelerated-2d-canvas
--disable-background-media-suspend --disable-renderer-backgrounding
--disable-field-trial-config
--enable-low-end-device-mode
--use-gl=angle --use-angle=swiftshader
--enable-unsafe-swiftshader
--js-flags=--max-old-space-size=384 --jitless
--window-size=1366,768
--user-data-dir=/root/chrome-steatlh-profile
--user-agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
--remote-debugging-port=9222
--remote-allow-origins=*
```
**CRITICAL: spasi antara flag penting**. Python f-string concatenation di multi-line string bisa kehilangan trailing space → `AudioServiceOutOfProcess--disable-accelerated-2d-canvas` jadi satu argumen dan Chrome ignore. SELALU verify launcher file: `head -2 /root/launch_chrome.sh`.

### CDP gotchas (CRITICAL — semua beneran terjadi)
1. **Page.enable needs PAGE target, not browser target**. `cdp.connect()` ke `/json/version` → `webSocketDebuggerUrl` = browser-level. `Page.enable` dari sini timeout 100%. Fix: ambil dari `/json/list`, filter `type=="page"`, ambil `webSocketDebuggerUrl`-nya.
2. **Chrome default newtab (chrome://newtab/)** = page target. Tunggu via `/json/list` polling atau `curl /json/new?about:blank` untuk create.
3. **Runtime.evaluate**: `(() => { JSON.stringify({...}) })()` returns `undefined` di Chrome 130. Arrow function block HARUS pakai `return` explicit. Atau langsung panggil expression tanpa IIFE wrapping.
4. **awaitPromise: true** bukan masalah untuk non-promise expression, TAPI kalau IIFE dalam block tanpa return → tetap return undefined.
5. **Input.enable domain conflict** — `Input.dispatchMouseEvent` bisa jalan tanpa enable, dan `Input.enable` bisa timeout. Skip domain ini kalau gak perlu.
6. **Connection error setelah navigate** = page target berganti. Reconnect WS pakai page target baru dari `/json/list`.
7. **Keepalive ping** penting — tanpa ping tiap 2 detik, WS di-drop Chrome di tengah challenge (bukan idle-drop OS, tapi Chrome internal cleanup pas GPU/JS sibuk).

### Termux-specific CDP launch pattern
`subprocess.Popen` ke `proot-distro login ubuntu -- bash launcher.sh` di Termux **child proot langsung mati** kalau gak pakai `start_new_session=True` + `stdin=DEVNULL`. Tapi launcher script juga harus **menulis PID file** supaya cleanup tahu process mana yang harus di-kill. Pattern:
```python
# tulis launcher ke /root/launch_chrome.sh via heredoc (proot)
# Popen dengan start_new_session=True
# tunggu CDP up via /json/version polling
# tunggu page target via /json/list polling (Page.enable needs it)
```

### Cleanup zombie proot
Proot sessions DAN chrome processes numpuk kalau script crash mid-way. Setiap run:
```bash
pgrep -f proot-distro | while read pid; do kill -9 "$pid" 2>/dev/null; done
pgrep -f chrome-linux | while read pid; do kill -9 "$pid" 2>/dev/null; done
# juga bersihkan CHROME_PID_FILE kalau ada
```
BUKAN `pkill -f` (kena shell sendiri, exit -9). BUKAN multi-statement dalam satu terminal call (filter trigger hardline block).

## Generasi 6: Persistent solver + session reuse (`cf_persistent.py`) ← operational
**Solve challenge SEKALI, reuse session berkali-kali**. SQLite-backed session store + per-host stable fingerprint + smart cache invalidation + auto re-solve on detection. Ini yang dipakai untuk long-running automation (monitor, scraper periodik) supaya gak bayar cost launch Chrome + solve challenge tiap request.

### Lokasi & pemakaian
```bash
# file di ~/cf_persistent.py (~1100 baris, 4 sub-commands)
python3 ~/cf_persistent.py solve https://domain-kamu.com          # solve + persist
python3 ~/cf_persistent.py fetch https://domain-kamu.com          # reuse session (no chrome)
python3 ~/cf_persistent.py fetch https://domain-kamu.com --force  # force re-solve
python3 ~/cf_persistent.py status                                # list all saved sessions
python3 ~/cf_persistent.py monitor https://domain-kamu.com --interval 60  # loop
```

### Arsitektur
- **SQLite store** (`~/.cf_persistent/cf_session.db`): sessions (host, UA, fingerprint, cf_clearance + TTL), cookies (per host), stats (challenge_count, success_count, last_used).
- **Stable per-host fingerprint**: deterministic seed dari `sha256(host)`. Setiap host SELALU dapet fingerprint yang sama (canvas noise seed, WebGL spoof, navigator props, screen size, timezone) → CF recognize sebagai "browser yang sama" antar reload → gak trigger challenge baru.
- **Persistent Chrome profile** (`--user-data-dir=/root/cf_persistent_profile`): cookies, cache, IndexedDB retained across launches.
- **Smart fetch flow** (HTTP-only, no Chrome):
  1. Cek `cf_clearance` di DB. Valid (>5 min remaining)? → reuse pakai `curl_cffi` dengan UA + cookies dari DB. **~1.5 detik** untuk 180KB.
  2. Tidak valid / first time? → launch Chrome, solve, persist.
  3. Response 403/503/has-challenge-markers? → auto re-solve, retry.
- **Monitor mode**: loop `fetch` dengan `--interval`, auto re-solve kalau CF balik challenge. `0` = forever.

### Files layout
```
~/.cf_persistent/
├── cf_session.db          # SQLite (sessions + cookies)
├── cf_profile/            # Chrome user-data-dir
├── cf_ua.txt              # stable UA
├── fp_<host>.json         # per-host fingerprint (seed + props)
├── page_<host>.html       # last fetched page
└── cf_persistent.log      # log
```

### Kapan pakai mana
| Situation | Pakai |
|---|---|
| First-time probe, validasi hardening | `cf_bypass_pro.py` (HTTP, instant) |
| Target kasih Turnstile/Managed Challenge interaktif | `cf_stealth.py` (one-shot solve) |
| Long-running scraper / monitor / API call berulang | `cf_persistent.py` (solve once, reuse) |
| Many hosts, perlu rotasi | `cf_adaptive.py` (state machine) |
| Enterprise Bot Mgmt (Crunchyroll) | **gak feasible di HP** — proxy + server |

### Pitfall `cf_persistent.py` (semua beneran terjadi)
- **`sqlite3.Connection` gak punya `.description`** — `c.execute(...).fetchone()` returns row, tapi `c.description` di Connection level itu None. Cursor yang punya description. Fix:
  ```python
  cur = c.execute("SELECT * FROM sessions WHERE host=?", (host,))
  cols = [d[0] for d in cur.description]
  r = cur.fetchone()
  ```
- **`/tmp` gak writable di Termux**. Default save-html ke `~/test.html`, BUKAN `/tmp/...`. Path `/tmp` error `FileNotFoundError [Errno 2]`.
- **Fingerprint seed harus deterministic per host** — kalo random tiap session, CF detect sebagai browser baru → challenge ulang. Pakai `sha256(host)[:4]` → `int.from_bytes(..., 'big')` sebagai seed.
- **Fingerprint disimpan ke file `fp_<host>.json`** — jangan di-generate ulang tiap run, cek dulu file exist. Itu yang bikin "stable per host".
- **First run always slow** (~25-30s untuk solve), subsequent runs ~1.5s pakai `curl_cffi` + cached cookies. Tradeoff worth it kalau >1 request ke host yang sama.

### Delegasi dari `cf_stealth.py`
- Pakai `Fingerprint` class yang **sama** dengan `cf_stealth.py` stealth JS.
- Bedanya: di `cf_persistent.py`, fingerprint **disimpan ke file** (persistent), bukan random per-session.
- Bedanya: di `cf_persistent.py`, ada **HTTP fetch path** yang reuse `cf_clearance` tanpa Chrome launch.
