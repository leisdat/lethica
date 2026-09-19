# Scrape pagination — limit contract + multi-page scrapePages (proven Aug 2026)

Fix "data scrape kurang lengkap / datanya dikit" pada extension hub: root cause
selalu salah satu dari (a) extension `section(id)` gak terima `limit` sama sekali,
(b) extension terima tapi hardcode 1 halaman. Core sudah benar — kontraknya
yang dilanggar extension.

## 1. Ukur situs DULU sebelum tulis paginasi
```bash
UA="Mozilla/5.0 (Linux; Android 13; SM-A515F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36"
# item per halaman
curl -s -A "$UA" "https://<site>/<list-path>/" -o ~/pg.html && grep -c 'detpost\|class="bs' ~/pg.html
# kedalaman paginasi
grep -oE 'page/[0-9]+/' ~/pg.html | sort -u
```
Tulis file scratch ke `~` (BUKAN /tmp — read-only di Termux).

## 2. Pola URL halaman 2+ (beda per situs, TEST keduanya)
- otakudesu: `/ongoing-anime/` → `/ongoing-anime/page/2/`
- anichin path polos (`/ongoing/`, `/completed/`, `/genres/x/`) → `/ongoing/page/2/`
- anichin ber-query (`/seri/?status=&type=&order=popular`) → `/seri/page/2/`
  **TANPA query**. Format `/seri/page/2/?status=...` balikin **0 byte HTTP 200**
  (bukan 404!) — jangan salah baca jadi "halaman habis". Kalau halaman paginasi
  balik 0 byte, coba buang query string-nya.

## 3. Kontrak limit (server ↔ extension)
- Core: `args = limit > 0 ? [sectionId, limit] : [sectionId]`; hasil di-slice ke
  limit SETELAH normalize. Jadi extension harus return minimal sebesar limit
  kalau datanya ada.
- Extension: `section(id, limit = 0)`. limit<=0 → 1 halaman default. limit>0 →
  loop maks `ceil(limit/PAGE)+2` halaman, dedupe ID antar halaman (Set), stop
  saat halaman kosong (added=0) / fetch gagal / limit tercapai.
- Home prefetch 12/section (ringan); "Lihat semua"/catalog = 200.

## 4. scrapePages — varian otakudesu (li.detpost, PAGE=24)
```js
async function scrapePages(baseUrl, limit = 0) {
  const PAGE = 24; // ukur per situs!
  const want = limit > 0 ? limit : PAGE;
  const out = [], seen = new Set();
  const maxPages = limit > 0 ? Math.ceil(want / PAGE) + 2 : 1;
  for (let page = 1; page <= maxPages; page++) {
    const url = page === 1 ? baseUrl : `${baseUrl.replace(/\/?$/, "/")}page/${page}/`;
    let html;
    try { html = await fetchHtml(url); } catch { break; }
    const $ = cheerio.load(html);
    let added = 0;
    $("ul li .detpost, li.detpost").each((_, el) => {
      if (out.length >= want) return;
      const $el = $(el);
      const a = $el.find(".thumb a[href*='/anime/'], a[href*='/anime/']").first();
      const aid = slugFrom(a.attr("href") || "");
      if (!aid || seen.has(aid)) return;
      const title = cleanTitle($el.find("h2.jdlflm, h2.jdlanime").first().text() || a.attr("title") || a.text());
      if (!title) return;
      const thumb = $el.find("img").first().attr("src") || "";
      const ratingMatch = ($el.find(".epztipe").first().text() || "").trim().match(/(\d+[.,]\d+)/);
      const epMatch = ($el.find(".epz").first().text() || "").trim().match(/(\d+)/);
      seen.add(aid);
      out.push({
        id: aid, title, year: null, type: "anime", thumbnail: thumb,
        rating: ratingMatch ? ratingMatch[1] : undefined,
        episodes: epMatch ? parseInt(epMatch[1], 10) : undefined,
      });
      added += 1;
    });
    if (out.length >= want) break;
    if (added === 0) break; // halaman kosong → habis
  }
  return out.slice(0, limit > 0 ? limit : undefined);
}
```

## 5. scrapePages — varian anichin (article.bs, PAGE=20, query-aware)
```js
async function scrapePages(baseUrl, limit = 0) {
  const PAGE = 20;
  const want = limit > 0 ? limit : PAGE;
  const out = [], seen = new Set();
  const maxPages = limit > 0 ? Math.ceil(want / PAGE) + 2 : 1;
  for (let page = 1; page <= maxPages; page++) {
    let url;
    if (page === 1) url = baseUrl;
    else {
      // paginasi anichin: /seri/page/N/ TANPA query (query hanya di halaman 1)
      const [path] = baseUrl.split("?");
      url = `${path.replace(/\/?$/, "/")}page/${page}/`;
    }
    let html;
    try { html = await fetchHtml(url); } catch { break; }
    const $ = cheerio.load(html);
    let added = 0;
    $("article.bs, div.bs").each((_, el) => {
      if (out.length >= want) return;
      const $el = $(el);
      const a = $el.find("a.tip, a[href]").first();
      const id = slugFrom(a.attr("href") || "");
      const title = cleanTitle(a.attr("title") || $el.find(".tt h2").first().text() || a.text());
      if (!id || !title || /-episode-\d+/i.test(id) || seen.has(id)) return;
      const thumb = $el.find("img").first().attr("src") || "";
      const ratingText = ($el.find(".rating strong").first().text() || "").trim();
      seen.add(id);
      out.push({
        id, title, year: null, type: "donghua", thumbnail: thumb,
        rating: /^\d/.test(ratingText) ? ratingText : undefined,
      });
      added += 1;
    });
    if (out.length >= want) break;
    if (added === 0) break;
  }
  return out.slice(0, limit > 0 ? limit : undefined);
}
```

## 6. Verifikasi (wajib, end-to-end)
```bash
node --check extensions/<id>/index.js
pm2 restart nova   # atau restart server hub
curl -s "http://127.0.0.1:3001/api/section?source=<src>&id=<section>&limit=200" \
  | grep -o '"id":' | wc -l   # harus > ukuran 1 halaman
```
Hasil terverifikasi Aug 2026: otakudesu ongoing 24→116 (habis), completed
24→200 (cap); anichin ongoing 20→99, completed 20→200, popular 20→38,
movie 20→40 (popular/movie memang cuma segitu — habis, bukan bug: bedakan
"kena cap" vs "habis" dari jumlah vs limit).

## 7. Debug UI terkait (race condition render)
Error `Cannot set properties of null (setting 'textContent')` di view async =
user pindah view di tengah `await` → DOM dibuang → element null. Fix di view:
`if (activeView !== '<view-id>') return;` setelah tiap `await` berat, dan
null-check sebelum `el.textContent = ...`.
