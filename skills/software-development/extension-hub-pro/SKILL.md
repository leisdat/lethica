---
name: extension-hub-pro
description: "Use when editing Extension Hub Pro (Nova): extensions, watch player, UI, server."
---

# Extension Hub Pro — nambah & debug extension

> **COMPACT-SURVIVAL SKILL**: dibuat biar gak ngulang inspect tiap session kena auto-compact. Load skill ini (skill_view name=extension-hub-pro) SEBELUM kerja apa pun di project ini — semua fakta path/port/global/symbol SUDAH terverifikasi di bawah, tinggal pakai. Jangan mulai dari `ls`/`search_files` ulang kalau belum baca skill ini.

Project: `~/extension-hub-pro` (Node, server port **3001**, UI `app/ui/`).
Test: `node test/run-all.js` (94+ pass). Extension jalan di **worker terisolasi** (`core/isolatedRuntime.js`).

## Trigger
- "nambah extension X" / "extension gak muncul di UI" / "worker keluar (code 1)" / "poster kosong" / "hapus extension X" / "hapus fitur <tab>"

## Urutan WAJIB nambah extension (jangan skip step 6!)

1. **Analisis situs dulu** (endpoint AJAX, format stream, ada DRM/login?). Kalau user kirim **file .har** dari DevTools → itu jalan tercepat, langsung parse:
   ```python
   import json; h=json.load(open('file.har'))
   for e in h['log']['entries']: print(e['request']['method'], e['request']['url'])
   ```
   HAR sering **tidak menyimpan response body** (`content.text` kosong) — ambil URL-nya lalu **replay pakai curl** dengan header `Origin`/`Referer` yang sama.

2. `mkdir -p extensions/<id>/lib`

3. `manifest.json` — field WAJIB (kalau kurang → `createExtension: manifest invalid`):
   ```json
   {"id","name","version","category","description","author",
    "entry":"index.js",
    "capabilities":["search","getDetail","getEpisodes","getEpisodeSources","latest","trending","sections","section"],
    "permissions":["network"], "icon","license","homepage"}
   ```
   `permissions` harus `"network"` (BUKAN `"net"`).

4. `lib/http.js` + `lib/catalog.js` + `lib/detail.js` — extension **boleh `require` file dalam foldernya sendiri**, sandbox tidak memblokir require. Sandbox gate hanya soal KONEKSI.

5. `index.js` → `createExtension({manifest, search, getDetail, getEpisodes, getEpisodeSources, sections, section, latest, trending})`.
   `sdk/extension.js` sudah diubah supaya **meneruskan capability opsional** (`sections/section/latest/trending`) — kalau balik ke versi lama, 4 fungsi itu hilang tanpa error.

6. **DAFTARKAN KE REPO + RE-SIGN** ← ini yang bikin muter-muter:
   - UI baca daftar extension dari **`repo/extensions.json`**, BUKAN dari folder `extensions/`.
   - Tambah manifest (tanpa `dir`) ke array `extensions`, lalu:
     ```bash
     node scripts/sign-repo.js     # WAJIB, kalau tidak signature invalid
     ```
7. **Install + enable** — edit `.data/state.json` (gitignored):
   ```json
   "installed": {"<id>": {"version":"1.0.0","installedAt":"..."}},
   "enabled":   {"<id>": true}
   ```
   `POST /api/extensions/install` cuma jalan kalau id-nya sudah ada di repo signed.

8. **Restart server** (lihat pitfall ghost process) → verifikasi.

## Cara hapus extension/fitur

### Hapus extension (extension scraper)
1. **Uninstall** via API: `POST /api/extensions/uninstall` → `{"id":"<id>"}`. Atau patch `.data/state.json` langsung (hapus dari `installed` + `enabled`).
2. **Hapus dari repo** (`repo/extensions.json`) — hapus entry dari array `extensions`.
3. **Re-sign**: `node scripts/sign-repo.js` — WAJIB, kalau tidak signature invalid.
4. **Hapus folder**: `rm -rf extensions/<id>/`.
5. **Restart server** → verifikasi: `curl localhost:3001/api/state` — extension tidak muncul.

### Hapus fitur UI (tab/halaman/komponen)
1. **index.html** — hapus tombol navigasi (sidebar + bottom-nav), cari `data-view="<id>"`.
2. **core.js** — hapus `case '<id>':` dari switch, hapus dari `titles` map.
3. **views/<file>.js** — hapus fungsi `render<View>(c)` + fungsi pendukungnya.
4. **ui.js** — hapus card component khusus kalau ada (mis. `comicCard`).
5. **app.css** — hapus CSS khusus (mis. `.comic-card`, `.carousel-comic`, `.grid-comic`).
6. **Cek referensi lain** — home.js mungkin masih panggil fungsi? search.js? filter category? Bersihkan.
7. **Tidak perlu restart** — UI statis, langsung apply.

### Catatan
- Hapus extension: **restart server** wajib (repo + state).
- Hapus fitur UI: **tidak perlu restart** — file statis langsung serve.
- Kalau setelah hapus extension, user tetap mau extension lain enabled → enable via API atau patch state.json.
- `repo/` dan `keys/` gitignored — perubahan repo tidak ikut commit.

## Baptisto — "iklan embed ke-lempar" fix (2026-09-09)
- Keluhan: pas streaming dari baptisto, "ada iklan di embed, gak bisa play, ke-lempar". Root cause BUKAN di scraper — resolver OK (morencius embed → packer decode → m3u8 acek-cdn bekerja, ada juga mirror .txt wildflowerartisanworks). Yang salah di **UI detail.js**: (1) `activeServer = servers[0]` default = iframe morencius (halaman JS penuh popunder/video_ad) bukan HLS direct di urutan kedua; (2) gak ada hls.js → m3u8 gak bisa play native di Chrome/Android → user cuma bisa pakai iframe iklan.
- Fix 3 lapis di detail.js + UI: (1) **rank servers** — `rank = s => mp4/hls ? 0 : iframe/embed ? 2 : 1; servers.sort(...)` di `openEpisode` sebelum pilih `servers[0]`; (2) iframe embed sekarang `sandbox="allow-scripts allow-same-origin allow-presentation"` + `referrerpolicy="no-referrer"` (popunder keblokir); (3) **hls.js lokal** `app/ui/vendor/hls.light.min.js` (v1.5.13) + `app/ui/js/hls-helper.js`.
- **PITFALL KRITIS canPlayType**: `video.canPlayType('application/vnd.apple.mpegurl')` di Chrome Android return **"maybe"** padahal native HLS-nya MATI → helper skip hls.js → video load m3u8 native → gejala "player muncul, 0:00, error/placeholder". FIX: SELALU pakai hls.js bila `Hls.isSupported()` (MSE), jangan percaya canPlayType. `removeAttribute('src') + load()` dulu sebelum attachMedia (cegah fetch native ganda). Helper: MutationObserver (video baru) + listener `loadstart` capture (video sama ganti src via selectServer/watchTo) + recoverMediaError/startLoad 1x masing-masing.
- CORS HLS acek-cdn OK: manifest/variant/seg `.ts` semua `Access-Control-Allow-Origin: *` (dicek curl + Origin header) — CDN lain gagal play? cek CORS seg dulu.
- HLS token acek-cdn expired (`e=129600` = 36 jam) → selalu re-resolve sources tiap buka, jangan cache URL HLS.

## otakudesu-fit — pitfall kritis slug series & sinopsis (2026-09-09)
- **Slug series ≠ slug episode**: `/series/{slug-episode}/` sering SALAH (cth episode `otome-game-sekai-...-episode-1-...` → series asli `otomege-sekai-...`). Homepage WordPress balikin **200 + judul "Otaku Desu"** (BUKAN 404) → scraper senyap parse homepage → detail/episodes kosong semua. **WAJIB validasi marker halaman seri** (`/eplister|eplist/` — JANGAN pake `bxcl`, homepage juga punya itu!) dan kalau miss → resolve slug asli dari halaman episode: fetch `{id}-episode-{1|2|10}-subtitle-indonesia/` → regex `href='.../series/...' aria-label='All Episodes'`.
- Sinopsis: kumpulin SEMUA paragraf `.entry-content p` (join \n\n), buang boilerplate SEO (Watch/Download/Stream/don't forget) + paragraf <40 char. Judul Mal-type cuma punya 1 kalimat (64 char) — itu normal, bukan bug.
- Halaman episode .fit **GAK PUNYA link download** (1 mirror iframe blogger doang; teks "Download" = SEO boilerplate). Sheet UI deteksi: `!linkServers.length && !videoServers.length` → tampil notice "Source ini tidak menyediakan link download" (renderEpisodeSheet detail.js).

## drakorid premium bypass (2026-09-02) — episode PREMIUM bisa di-stream

**Temuan kunci**: drakorid punya gate premium early-access (ep 6/7) & daily limit (1x/hari per device+IP) di route `/watch-{lite|max}/{slug}/{ep}`. TAPI ada **endpoint myapi yang return direct MP4 TANPA gate sama sekali**:

```bash
# 1. Ambil halaman detail → extract var token + var mId:
#    var token = "wh.xxx"; var mId = 5053;
# 2. POST ke myapi:
curl -s "https://drakorid.co/myapi/episode_detail.php" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "token=$TOKEN&id=$MID&episode=7"
# → {"status":1,"streaming_premium":"http://admin.drakor.la/go/files/106523","streaming":"106523",...}
# 3. Follow redirect:
curl -sIL "http://admin.drakor.la/go/files/106523" -A "Mozilla/5.0"
# → 302 → http://sk19.drakor.cc/files/0-2026-09-02-....mp4 (video/mp4, HTTP 206 Range OK)
```

**Fakta penting**:
- `episode_detail.php` TANPA cookie, TANPA referer, TANPA login — cukup `token` (inline di halaman detail: `var token = "..."`) + `id` (var mId) + `episode` (nomor).
- `admin.drakor.la/go/files/{fid}` juga TANPA gate — 302 ke CDN `sk*.drakor.cc/files/*.mp4`. MP4 full (~396MB), `Accept-Ranges: bytes`, bisa seek. HTTP (bukan HTTPS) — player harus izinkan mixed content atau pakai proxy.
- Berlaku untuk SEMUA episode (1-7), termasuk yang PREMIUM early-access. Ini bypass total: no premium check, no guest-limit, no daily limit.
- Gate lain yang ditemukan: guest stream 1x/hari = **IP-based** (rotating device_id TIDAK membantu); member free kena "batas maksimal download harian 1/hari" per **device_id + IP** (rotasi akun tidak cukup); premium ep 6/7 = early-access sampai tanggal tertentu (server-side PHP, cek pesan `member gratis baru bisa akses pada`).
- 4 cookie session drakorid: `device_id` (HttpOnly, penentu tracking limit), `PHPSESSID`, `login`, `jwtlogin`.

**Implementasi di extension** (`extensions/drakorid/lib/detail.js`):
- Urutan di `getEpisodeSources()`: (1) coba myapi dulu → kalau `status===1 && json.streaming_premium` push stream `{type:"mp4", url: fidUrl}` → return; (2) fallback watch-* lite/max seperti biasa (HLS adaptive) kalau myapi gagal.
- `session` di-require dari `./http.js` (bukan langsung `./session.js`) untuk markExhausted/invalidate.
- Stream myapi dilabel `MP4 {json.streaming}` (contoh: "MP4 106520").
- Test API: `GET /api/sources?source=drakorid&episodeId={slug}-ep-{n}` → `{"ok":true,"data":[{"id":"drakor-myapi-1","label":"MP4 106520","type":"mp4",...}]}`.

## otakudesu-fit (tambah 2026-08-30) — clone anichin
- `otakudesu.fit` BEDA dari `otakudesu.blog` (katalog beda; cek dua-duanya kalau judul gak ketemu). `.fit` pakai struktur tema sama persis kayak anichin.cafe → dibuat sebagai clone `extensions/otakudesu-fit/` (BASE + path `/series/` + `slugFrom` strip `series/`). 6 ext aktif: otakudesu, anichin, drakorid, drakorkita, mdtv, otakudesu-fit.
- **Pitfall `.epx`**: di `/ongoing/` & `/completed/`, `.epx` berisi NOMOR EPISODE ("Ep 21"); di `/series/?status=`, `.epx` berisi STATUS ("Ongoing"/"Completed"). Fix: deteksi regex `/^Ep\s*\.?\s*(\d+)/i` → kalau match jadi `episodes`, else `status`; section ongoing/completed kasih `hintStatus` (param ke-3 `scrapePages`).
- **Search cache**: `core/sources.js` → `searchCache = ttlCache({ttlMs:10*60*1000})` di sekitar `search()`; key `search:<sourceId|all>:<fingerprint>:<query lowercased>`. Fingerprint = sorted list of enabled extension IDs — otomatis miss cache saat extension di-enable/disable/install tanpa perlu explicit invalidation. Cold ~5s → warm ~3ms.
- **Search cache jangan simpan total failure**: kalau `errors.length === exts.length` (semua source gagal), skip cache — biar retry berikutnya nembak ulang, bukan nembak cache kosong. (transient outage gak bikin search mati 10 menit.)
- **ttlCache.get(key)**: method baru di `sdk/cache.js` — ngambil value tanpa auto-set. Dipakai oleh search cache untuk conditional caching. Additive, gak ngerusak extension yang pake `getOrSet`.
- **normalize pass-through** (`sdk/models.js`): `normalizeDetail` daftar field opsional (`year`,`studio`,`season`, dll) HARUS didaftarkan di array `for (const k of [...])` biar gak dibuang; `normalizeSearchResult` juga (status/subDub/quality/addedAt). Kalau field dari extension gak muncul di API → cek dulu normalizer, bukan scraper.
- `POST /api/extensions/install` jalan hanya kalau id sudah ada di repo signed.

## Hardening 2026-09-01 (audit 2) — worker pool, sandbox, crypto
- **Worker pool limiter**: `core/isolatedRuntime.js` — `MAX_CONCURRENT_WORKERS=6` (semaphore FIFO + cancel-on-timeout). Request ke-7+ antri sampai ada slot; `WORKER_BUSY` kalau 20s gak dapat slot. Semaphore: `_acquireSlot()` → `{promise, cancel}`, `_releaseSlot()` serahin ke waiter berikutnya. **Jangan pernah resolve slot tanpa fungsi release** (slot leak permanen).
- **Crash cooldown 30s**: worker crash/exit sendiri → `recordCrash(id)`; request berikutnya dalam 30s balas `WORKER_COOLDOWN` (cegah spawn-loop OOM).
- **downloads.js**: `MAX_JOB_SIZE=2GB` + `MAX_CONCURRENT_DOWNLOADS=3` (sisanya status `queued`, antri FIFO). Fix resume: server abaikan Range (HTTP 200) → truncate file lama, bukan append (sebelumnya corrupt). Slot release idempotent (`_active/_released`).
- **Sandbox symlink escape FIXED** (`sdk/workerSandbox.js`): require sekarang cek `fs.realpathSync` — symlink dalam folder extension yang nunjuk ke luar sandbox DITOLAK.
- **Crypto signature consistency FIXED** (`sdk/signature.js`): verifier sekarang pakai `extractSignedPayload` (3 field: schemaVersion/repository/extensions) SAMA dengan `sign-repo.js` — sebelumnya verifier spread semua key → mismatch kalau repo punya field tambahan.
- **repoClient SSRF guard**: `loadRemote` blokir IP private saat `requireSignature=true` (produksi). Test fase2 pakai `allowInsecure` + localhost → guard dilewati.
- **storage.js fsync**: `save()` pakai `fs.openSync` + `writeFileSync` + `fsyncSync` + `closeSync` sebelum rename (cegah korup kalau crash).
- `sdk/cache.js`: tambah `destroy()` (clearInterval + clear store/locks).

## Auth (2026-09-01) — mutasi wajib X-Auth-Token
- Semua endpoint **mutasi** (install/uninstall/enable/disable/update, repo/refresh, settings POST, downloads/start + kontrol, auto-update/check, permissions/reset) balas **401** tanpa header `X-Auth-Token`.
- Token: `core/auth.js`, disimpan `.data/auth.json` (gitignored), di-load saat start (restart gak ganti token). Baca via `python3 -c "import json;print(json.load(open('~/extension-hub-pro/.data/auth.json'))['token'])"`.
- UI dapat token via **inject HTML**: server inject `<script>window.EH_AUTH_TOKEN=...</script>` sebelum `</head>` di index.html (bukan endpoint publik). `api()` di core.js otomatis kirim header.
- **Debug curl WAJIB tambah `-H "X-Auth-Token: $TOKEN"`** ke endpoint mutasi, kalau tidak 401. GET endpoint tetap publik.
- **SSRF guard** di `/api/downloads/start`: URL ke IP private (127.0.0.1, 10.x, 192.168.x, 172.16-31.x, localhost, 0.0.0.0) → 400 "SSRF blocked". URL publik normal tetap jalan. (Sync, cek IP literal + hostname umum.)

## Verifikasi (query param `source`, BUKAN `sourceId`)
```bash
curl -s "localhost:3001/api/sections?source=<id>"
curl -s "localhost:3001/api/section?source=<id>&id=terbaru&limit=3"
curl -s "localhost:3001/api/detail?source=<id>&id=<slug>"
curl -s "localhost:3001/api/episodes?source=<id>&id=<slug>"
curl -s "localhost:3001/api/sources?source=<id>&episodeId=<epid>"
```
Cek `repo.extensions` juga: `curl -s localhost:3001/api/state`.

## Cast ke TV (Chromecast) — sudah ada
- `app/ui/js/cast.js` (load setelah debug.js di index.html): sender SDK v4 (`gstatic .../cast_framework.js`), eksplisit — tombol, bukan auto-hijack. `window.castMedia({url,title,subtitle,time})` → requestSession + loadMedia (StreamType.BUFFERED, contentType video/mp4, metadata judul). Non-Chrome / gagal load SDK → semua `.cast-btn` dihapus.
- Tombol "TV Cast": (1) watch player `watch.js` → `window.castCurrent()` pakai `videoElement.currentSrc` + `currentTime` (resume); (2) sheet detail `detail.js` → `window.castSheet()` pakai `window.__activeVideo` {url,title,label} — di-set di `openDetail`/`selectServer` saat server aktif type mp4/hls. **Onclick cast TANPA arg** (url via global, bukan string) → bebas masalah escape judul.
- MDTV = MP4 langsung dari R2 (tanpa token/referer) → TV stream langsung dari internet. Prasyarat: TV + HP satu WiFi, user pakai **Chrome/Edge** (Cast SDK), Chromecast/Android TV "Chromecast built-in".
- LIMITASI: konten HLS / embed iframe TIDAK bisa di-cast (media type unsupported) — tombol tetap tampil, toast gagal. File download lokal (`/downloads/x.mp4`) bisa di-cast hanya kalau TV akses IP-LAN HP.

## WATCH PLAYER — navigasi episode & skip (2026-09-08)

File: `app/ui/js/views/watch.js` (+ CSS `.watch-*` di `css/app.css`). Edit PAKAI `patch`, JANGAN `write_file` (file punya logic existing). Restart server TIDAK perlu — UI statis.

### Fakta terverifikasi struktur watch.js (364 line)
- Global tersedia: `esc`, `api`, `castMedia`, `castCurrent`, `switchView`, `toast`, `fmtTime`, `ICON` (keys: `rewind10`, `forward10`, `play`, `pause`, `prev`, `next`, `info`, `cast`, `gear`), `window.__activeVideo`, `activeView`.
- State global: `watchPlaylist` (array), `watchIndex` (int), `watchMime`, `watchAutoNext` (bool), `watchSkip` (bool).
- Navigasi episode udah ada: `window.watchPrev`, `window.watchNext`, `window.watchTo(i)`, `window.watchEnded` (`v.onended` → auto-next kalau `watchAutoNext`).
- Tombol prev/next di controls: `<button class="watch-btn nav prev/next" onclick="watchPrev()/watchNext()">ICON.prev/next</button>` — enable/disable via `updateNavButtons()` (prev disabled kalau index 0, next disabled kalau index terakhir).
- Chip episode: `buildEpisodeChips()` render `#watchEpisodes` pakai `.chip` + `.active` (current `watchIndex`); klik → `watchTo(i)`.
- Skip intro/auto: `bindSkipControls()` toggle `.watch-tool.skip` → set `watchSkip`/`watchAutoNext`; `applySkip()` pakai `SKIP_INTRO_END` (ms, default 85s), `SKIP_OUTRO_TAIL` (ms, default 20s), `SHORT_EP_THRESHOLD` (ms, default 120s) + `v.currentTime` + `v.duration`.

### Cara nambah fitur ke watch player
1. **Cek dulu fungsi yg udah ada** — `search_files` `watchPrev|watchNext|watchTo|watchSkip` di `watch.js`. Jangan double-implement (fitur nav prev/next/auto-next & skip SUDAH ADA, #1/#3 di request user ternyata udah jalan; cuma butuh verifikasi/gaya).
2. **Tambah konstanta** di bagian atas watch.js (mis. `const SKIP_INTRO_END = 85000;`) — PASTIKAN gak undefined (ReferenceError saat load = putih).
3. **Tambah tombol** di string HTML controls (pakai `ICON.<key>`, `onclick="fnName()"`).
4. **Tambah handler** `window.fnName = function(){...}` — simpan ke global biar `onclick` inline jalan.
5. **Tambah CSS** di `css/app.css` block `/* WATCH PLAYER */` — `.watch-tool.active` HARUS di-style (toggle class tanpa style = gak kelihatan aktif): `.watch-tool.active{background:var(--accent);color:#fff}`. `.chip.active` & `.watch-ep-chips` SUDAH ada.
6. **Verifikasi** (lihat di bawah) — jangan claim beres sebelum cek served file.

### Navigasi prev/next episode di SHEET DETAIL (detail.js, fix 2026-09-09)
- Fitur prev/next ADA DI DUA TEMPAT: (1) watch player `watch.js` (playlist download, sort ascending, sudah benar), (2) **episode sheet `detail.js`** (streaming dari detail) — epNav + epPrev/epNext/toggleAutoNext/vSeek setelah renderEpisodeSheet.
- **ROOT CAUSE bug "prev/next kebalik"**: `window.__episodes` diisi urutan API MENTAH — banyak source return episode DESCENDING (terbaru dulu) → `eps[i-1]` loncat ke episode lebih TINGGI, `i+1` mundur. Fix WAJIB: sort ascending numeric sebelum dipakai: `window.__episodes = episodes.slice().sort((a,b)=>(parseInt(String(a.number).match(/\d+/)?.[0])||0)-(parseInt(String(b.number).match(/\d+/)?.[0])||0))` di `openDetail`. Sort di openDetail (bukan openEpisode) biar sekali per judul.
- `__currentEpisodeId` di-set di `openEpisode`; `toggleAutoNext` re-render sheet pakai `__serversCache` + `activeServer`; auto-next = `onended="if(window.__autoNext)epNext()"` di video player-frame.
- Verifikasi arah: simulasi node dengan list descending → prev harus episode lebih rendah. `node --check detail.js` WAJIB tiap patch (pitfall escape `\'`).

### Verifikasi edit watch player
```bash
# 1. syntax JS (wajib setelah tiap patch)
node --check app/ui/js/views/watch.js
# 2. symbol masih defined (gak ada ReferenceError pas load)
node -e "const s=require('fs').readFileSync('app/ui/js/views/watch.js','utf8'); ['watchSkip','watchAutoNext','SKIP_INTRO_END','SKIP_OUTRO_TAIL','SHORT_EP_THRESHOLD','watchPrev','watchNext','watchTo'].forEach(x=>console.log(x, s.includes(x)?'OK':'MISSING'))"
# 3. server serve versi BARU (path js/views/watch.js, BUKAN views/watch.js)
curl -s http://127.0.0.1:3001/js/views/watch.js | wc -c   # harus == byte file di disk
curl -s http://127.0.0.1:3001/js/views/watch.js | grep -c 'watchTo'  # fitur hadir
```
- **Path penting**: server serve `app/ui/js/views/watch.js` (URL `/js/views/watch.js`). URL `/views/watch.js` = 404. UI inject script `<script src="/js/views/watch.js"></script>` di index.html.
- Ghost process: kalau perubahan gak kelihatan, `pgrep -af "app/server.js"` → `kill -9 <pid>`, restart `node app/server.js`.

## Pitfalls (semua pernah kejadian)
- **Ghost node**: `pkill` / kill session cuma matiin bash wrapper — proses `node` anak tetap melayani request dengan core LAMA (patch seolah tidak berefek). Cari `pgrep -af "app/server.js"`, lalu **`kill -9 <pid node>`**. Start ulang: `terminal(background=true, command="cd ~/extension-hub-pro && node app/server.js")`.
- **"worker keluar (code 1)" massal** — penyebab klasik (3 lapis):
  1. **IDLE_MS=2000** di `core/isolatedRuntime.js` — setelah request pertama selesai, timer bunuh worker 2 detik kemudian. Request lain masih antri (serialisasi) → worker dibunuh di tengah proses → ALL queued requests gagal. **Fix: naikkan IDLE_MS ke 60000** (atau lebih). Sudah di-patch.
  2. **workerScript proses message CONCURRENT** — `parentPort.on("message", async ...)` tanpa serialisasi → 4 request berat berjalan bersamaan → 40 fetch HTTP paralel → OOM. **Fix: serialisasi pakai promise queue** (`core/workerScript.js`). Sudah di-patch.
  3. **Unhandled rejection/exception di worker** — promise rejection tak tertangkap bikin exit code 1. **Fix: handler `process.on("unhandledRejection")` + `"uncaughtException"`**. Sudah di-patch.
  - **Cascade: Home minta 5 section × 5 source = 25 worker** → OOM. **Fix: 1 section terbaik per source** (prioritas: popular → recommendation → terbaru → ongoing → completed → catalog).
  - **getFullCatalog cache race** — 4 request masuk bersamaan untuk section yang sama → semua fetch ulang. **Fix: promise lock** — request kedua nunggu yang pertama selesai.
  - **`getFullCatalog` tanpa try/catch** — timeout halaman → unhandled rejection → worker crash. **Fix: try/catch per halaman, skip yang gagal.**
    - **Cache result PARSED, bukan raw HTML** (voratoon fetchBrowse): kalau cache `getOrSet` return HTML string tapi caller mengharapkan array → `for (const it of page)` iterasi PER KARAKTER → catalog cuma 1 item + worker crash. **Fix: fetcher di dalam `getOrSet` harus parse dulu** (`getOrSet(key, async () => parseSeries(await fetchHtml(url)))`).
  - **Shared cache**: `sdk/cache.js` → `ttlCache({ttlMs})` dengan `getOrSet(key, fetcher)` + promise lock. Pakai di semua extension (voratoon/drakorid/drakorkita/otakudesu/anichin). Path require: `extensions/<id>/index.js` → `../../sdk/cache`; `extensions/<id>/lib/*.js` → `../../../sdk/cache`.
  - **Hotlink protection** (nekopoi dll): server blokir request dengan referer luar → 403. **Fix: `referrerpolicy="no-referrer"` di semua `<img>` external** (posterCard/comicCard/detail/extension icon).
  - `video.php` **server_id f1 sering HTTP 500** (server rotasi f1/f2/f3). `getEpisodeSources` drakorkita sudah di-patch dengan **failover loop f1→f2→f3** (coba server lain kalau 500 atau `file` kosong). Kalau tiba-tiba 0 stream lagi → cek dulu `curl "https://api.nonton.bid/c_api/video.php?is_mob=1&is_uc=0&t=<ts>&id=<epid>&qua=web&server_id=f2&cat=hs&tag=ind"` langsung, bukan asumsi extension-nya.
- **0 stream ≠ bug extension**: `getEpisodeSources` banyak pakai try/catch silent. Debug cepat: panggil `cApi("video.php",{...})` langsung via node dari folder extension (bukan via API server) → kelihatan 500/network error yang ditelan.
- **MDTV movie single-episode**: `/api/sources` pakai `episodeId=mdtv:<movieId>:1` (bukan movie id). `videoUrl` ada di `episodes[0].videoUrl` di response detail, bukan top-level.
- **Tunnel localhost.run URL rotasi** saat pm2 restart: ambil dari `tr -d '\r' < ~/.pm2/logs/nova-tunnel-out.log | grep -aoE "https://[a-z0-9]+\.lhr.life" | tail -1` (bukan `.localhost.run` — format sekarang `*.lhr.life`). **Tunnel bisa stuck setengah-mati**: pm2 bilang "online" tapi ssh connection-nya dead → URL lama balikin halaman `<h1>no tunnel</h1>` (UI nge-log `Unexpected token '<', "<h1>no tun"...`). Auto-reconnect loop di `nova-tunnel.sh` TIDAK selalu kick in (ssh hang, gak exit). Fix: `pm2 restart nova-tunnel` → URL BARU muncul dalam ~10s → kasih ke user. Server lokal tetap sehat, jadi ini masalah tunnel doang.
- **state.json `enabled` ke-reset** — sering BUKAN bug server: user disable extension di UI (tab Extensions). Cek `.data/state.json` dulu, kalau false tinggal enable via `POST /api/extensions/enable` atau patch JSON.
  - **gzip + cache-control server** (`app/server.js` serveStatic): pakai `zlib.gzipSync` + `Content-Length: gz.length` (jangan null → response 0 bytes). CSS 52KB→9.7KB, JS→30%. Cache-Control: JS/CSS `public, max-age=3600`, HTML `no-cache`.
  - **NOVA branding**: title "NOVA — Streaming Hub", favicon SVG inline, hero pakai `heroHTML()` helper di ui.js (1 sumber, semua view). Meta PWA: theme-color, apple-mobile-web-app.
- **Poster kosong / semua API error** → cek `enabled` di `.data/state.json` dulu (sering `false`).
- **`X is not defined` setelah split file** → import yang lupa dibawa saat pecah modul (mis. `const {BASE, fetchHtml} = require("./http.js")`).
- `runIsolated` di harness manual wajib **path ABSOLUT**.
- `/tmp` read-only di Termux — tulis ke `~`.
- `core/` diubah → restart penuh; `extensions/` → hot-reload.
- **VIEW FILE GOTCHA**: Jangan `write_file` untuk edit view JS — file-file di `app/ui/js/views/` punya existing logic (downloads.js punya startDownload, polling, filter). Selalu pakai `patch` untuk edit targeted. Kalau ke-overwrite, `git checkout -- app/ui/js/views/<file>.js` buat restore.
- **Async view render Wajib guard `activeView` + null check**: Fungsi `async render<View>(c)` yang melakukan `await Promise.all([...api calls])` setelah render HTML awal → user bisa pindah view di tengah await → DOM element tujuan (`#someId`) udah gak ada → `Cannot set properties of null (setting 'textContent')`. Fix: tambah `if (activeView !== '<view>') return;` segera setelah await, dan guard `if (el) el.textContent = ...` di setiap akses DOM. Pola ini sudah di-apply di extensions.js & settings.js. (Bug kelas yang sama mengenai 2 file.)
- **JANGAN `JSON.stringify(id)` DI ATTRIBUTE HTML `onerror`/`onclick`**: hasilnya bawa double-quote → tabrakan sama delimiter attribute `"..."` → handler ke-truncate jadi `this.outerHTML=extIconFallback(` → pas img fail load → `SyntaxError: Unexpected end of input` di `:1` (tanpa filename). Fix: pakai pola `\'` (escaped single quote) + `esc(id)`: `onerror="this.outerHTML=extIconFallback(\'' + esc(id) + '\')"`. Verifikasi: regex `onerror="([^"]*)"` harus nangkep string utuh, terus `eval(handler.replace('extIconFallback','globalThis.__fake'))` harus return bener. (Kejadian di extensions.js baris 97 & 175 — 2 SyntaxError `:1` di log debug.)
- **ESCAPE `\'` DI STRING JS (patch tool)**: kalau patch string literal yang mengandung `\'` (quote di-escape di dalam string, mis. `onclick="openCatalogAll(\'section\',...)"`), patch tool bisa nulis `\\'` (backslash literal + quote) ke file → `SyntaxError: Invalid or unexpected token`. **WAJIB `node --check <file>` setelah tiap patch** ke view JS, dan verifikasi string `onclick` dengan mengeval-kan kontennya: `new Function(html.match(/onclick="([^"]+)"/)[1].replace("openCatalogAll","globalThis.__fake"))()`.
- **URL HANDLER — query parsing setelah migrasi `url.parse()` → `new URL()`**: handler API yang dulu baca `parsed.query` (objek dari `url.parse`) harus dibaca `parsed.searchParams.get(...)` (URLSearchParams dari `new URL`). Kalau handler lama masih panggil `parsed.query` → undefined → endpoint balas error aneh ("endpoint not found" / parameter hilang). Cek semua handler saat migrasi: `search_files` untuk `parsed.query` & `parsed.search` → ganti ke `parsed.searchParams.get()` / `parsed.pathname`.
- **PERFORMA HOME — AGREGASI + CACHE** (fix lag): home JANGAN fetch 12+ endpoint serial (2x /api/state + /api/latest + N×/api/sections + M×/api/section). Sekarang: **GET /api/home** (app/server.js) -> sources.home() di core/sources.js = 1 fetch semua (latest + sections + isi 2 section terbaik/source + genre chips, paralel) dibungkus homeCache = ttlCache({ttlMs:90000}) dari sdk/cache.js. Frontend home.js cukup 1 api('/api/home') -> fillLatest/fillDynamicSections/fillGenreChips. Cold ~1.4s, warm ~32ms. Section baru home -> extend home() di sources.js, bukan tambah fetch.
- **HOME CACHE FINGERPRINT** (fix 2026-09-02): cache key home HARUS fingerprint extension aktif. Sebelumnya `key = "home:v1"` — user disable extension di UI tapi home masih nampilin data lama 90 detik. Fix: `const fp = enabledExtensions().map(e => e.id).sort().join(","); const key = \`home:v1:${fp}\``. Tiap toggle extension → fingerprint berubah → cache miss → dapet data baru. TAPI ini saja tidak cukup untuk kasus disable → enable dalam 90 detik (key-nya sama). BUTUH juga `clearHomeCache()` dipanggil saat enable/disable.
- **HOME CACHE INVALIDATION ON TOGGLE** (fix 2026-09-02): `enable()`/`disable()` di `manager.js` tidak pernah invalidate cache home. Akibatnya: user disable extension, balik ke Home, masih data lama. Fix: export `clearHomeCache()` dari `sources.js` (`homeCache.clear()`), panggil di handler HTTP `POST /api/extensions/enable` dan `POST /api/extensions/disable` di `app/server.js` — langsung setelah `manager.enable/disable()` sukses. Verifikasi: disable mdtv → `/api/home` langsung hilang section mdtv tanpa nunggu 90 detik.
- **JANK CSS MOBILE** (fix lag scroll): (1) backdrop-filter blur(20-24px) di topbar/bottom-nav = recalc blur tiap frame -> di mobile (<768px) turunin blur(10px) + bg lebih opaque; (2) cardIn stagger x48 card = jank -> animation:none di mobile + prefers-reduced-motion; (3) content-visibility:auto + contain-intrinsic-size: auto 320px di .section. JANGAN lepas aspect-ratio:2/3 di poster (layout shift).
- `repo/` dan `keys/` gitignored — perubahan `repo/extensions.json` TIDAK ikut commit, jadi di mesin/clone baru manifest harus didaftarkan ulang + re-sign.

## Account feature (2026-09-01) — auth lokal + favorit & riwayat

Fitur akun pengguna **lokal** (tanpa API eksternal), disimpan di `.data/accounts.json` (gitignored).

### Backend: `core/account.js`

Endpoint via `app/server.js` — semua pakai header `x-account-token`:

| Method | Endpoint | Auth | Fungsi |
|--------|----------|------|--------|
| POST | `/api/account/register` | No | `{username, password}` → `{ok, token}` |
| POST | `/api/account/login` | No | `{username, password}` → `{ok, token}` |
| GET | `/api/account/me` | Yes | profile user |
| GET | `/api/account/favorites` | Yes | list favorit |
| POST | `/api/account/favorites` | Yes | `{item:{id,title,source,poster,type,episode?,status?}}` |
| DELETE | `/api/account/favorites?id=...` | Yes | hapus 1 item |
| DELETE | `/api/account/favorites` | Yes | hapus semua |
| GET | `/api/account/history` | Yes | list riwayat |
| POST | `/api/account/history` | Yes | `{entry:{id,title,source,poster,type,episode?,progress?,watchedAt?}}` |
| DELETE | `/api/account/history` | Yes | hapus semua |

### Frontend: `app/ui/js/views/downloads.js` → `renderProfile(c)`

- Tab "Akun" di view Downloads: form login/register (username + password), setelah login nampilin username + tombol logout.
- Tabs: Favorit (grid posterCard) + Riwayat (list dengan watchedAt).
- Login state disimpan di `localStorage` key `eh-account-token`.
- Halaman "Akun" muncul di view Downloads (tab ketiga setelah "Download" + "Filter").
- **Tidak ada fitur register via UI** — login/register via API dulu, UI hanya login form.

### API request format (history add)
```json
POST /api/account/history
x-account-token: <token>
{"entry": {"id": "anichin_ep1", "title": "...", "source": "anichin", "poster": "", "type": "anime", "episode": "1", "progress": 0, "watchedAt": 1234567890}}
```

### Pitfall field naming
- `addFavorite` simpan item pakai field `source` (dari extension).
- `removeFavorite` & dedupe filter pakai `sourceId` — **tidak match** karena item disimpan dengan `source`, bukan `sourceId`.
- **Fix**: `removeFavorite` & dedupe harus cek item.source (bukan item.sourceId). Sama juga di `addHistory`/`removeHistory`.
- Konsisten: field penyimpanan = `source`, field query = `source`.

## UI Maintenance

UI di-serve statis dari `app/ui/` — **tidak perlu restart server** untuk edit HTML/CSS/JS. Hanya perubahan `core/` atau `app/server.js` yang butuh restart.

### Struktur
```
app/ui/
  index.html       # shell: sidebar (desktop) + bottom-nav (mobile) + overlay/sheet/toast
  css/app.css      # design system (Inter, 8px grid, dark/light, tokens)
  js/
    core.js        # state global, theme, navigasi (switchView, renderView, router URL)
    ui.js          # helpers: skeleton, posterCard, ICON, sheet, miniPlayer
    debug.js       # DEBUG CONSOLE v2 (2026-08-30): log terstruktur {kind,sev,msg,detail,ctx,count}, dedupe 5 dtk, persist localStorage (key `eh-debug-v2`) + restore antar-refresh, wrap fetch global = network monitor (tab Net, status+ms), snapshot sistem saat Copy (state ext enabled/disabled + repo status), filter tabs Semua/Error/Warn/Net, badge di row Settings. `window.openDebug/setDebugFilter/copyDebugLog/clearDebugLog/updateDebugBadge`. UI: overlay `#debugOverlay` (id: dbgEntries, dbgNet, dbgTabNet, dbgCount, dbgLogPane, dbgNetPane) + style `.dbg-*` di app.css.
    app.js         # bootstrap: router + init
    views/
      home.js      # renderHome (hero, latest, dynamic sections, explore chips)
      search.js    # renderSearch (search bar, type chips, source chips, results)
      explore.js   # renderExplore (Genres + Jadwal tabs, multi-source)
      detail.js    # openDetail + openEpisode + renderEpisodeSheet (sheet detail, player)
      extensions.js# renderExtensions (repo/installed tabs, extCard, install/enable)
      downloads.js # renderDownloads (download polling/filter) + renderProfile
      settings.js  # renderSettings (theme, priority, permissions, security)
```

### Nambah/Ubah navigasi
1. **index.html** — tambah/sembunyi tombol sidebar + bottom-nav, pastikan `data-view="<id>"`
2. **core.js** — tambah di `titles` map + `switch(view)` case
3. **views/<file>.js** — tulis fungsi `render<View>(c)`
4. Cek `app.js` `bootRoute()` untuk path cantik (URL `/latest`, `/complete` dll)

### Struktur Home (rebuild Aug 2026 — "lengkapi NOVA")
- Home kaya: hero → carousel **Update Terbaru** → **Lanjutkan Menonton** (localStorage `eh-watch-history`) → **section dinamis** → **genre chips**.
- Section dinamis = **semua source enabled** dengan capability `sections` (max 2 section/source, skip `terbaru` + `genre:*`). Data-driven — gak hardcode per source. Source lama (otakudesu/anichin/drakor*) gak punya capability `sections` → gak muncul di home, cuma di search/detail.
- **"Lihat semua"** → view `catalog-all` di `views/catalog.js`: `openCatalogAll(mode,title,sectionId,sourceId,pushRoute)`. Route: `/latest` (agregasi), `/catalog/<source>/<sectionId>`, `/genre/<slug>`. Fungsi `renderCatalogAllHead` + `fillCatalogAll` dipanggil dari `app.js` bootRoute.
- Genre chips home = kumpul semua section `genre:*` dari semua source (bukan cuma source pertama).

### UI polish komponen
- **posterCard** (ui.js): poster-img-wrap + overlay gradient + rating-pill + quality-badge + zoom hover
- **skeleton**: shimmer 1.6s + skPulse + stagger delay + border-radius
- **section names**: pake `sections()` API dari tiap source (`{id, name, type}`), bukan capitalize raw sectionId
- **search**: `/api/search?q=&source=` — filter per source didukung server + core

## Contoh nyata: drakorkita (streaming HLS bertopeng font)
`drakor.kita.mobi` + API `api.nonton.bid/c_api/` (header `Origin`/`Referer` = situs):
- `episode.php?movie_id=<first_ep_id>` → HTML daftar episode, ambil `data-epid`.
  `first_ep_id` diambil dari `onclick="loadEpisode('ID','hs','ind')"` di halaman detail.
- `video.php?id=<epid>&qua=web&server_id=f1&cat=hs&tag=ind` → `hls_key` + field `file`
  (format `[<font>480p</font>...]URL,[...]URL`).
- Embed URL `seniman1[hd].uyeshare.cc/e/<token>` → **404 kalau di-GET biasa**;
  kirim header **`X-Hls-Key: <hls_key>`** → balik M3U8 asli.
- Segment di M3U8 disamarkan jadi `/fonts/.../font-NNN.woff` (isinya video).
- Fallback: `video_hydrax.php` (abysscdn) & `video_p2p.php` (iframe).
- Player HLS harus bisa kirim custom header per-request; kalau tidak, proxy M3U8 di server hub.
Jangan buang waktu deobfuscate `a.js` (obfuscated berat) — HAR + replay curl jauh lebih cepat.
