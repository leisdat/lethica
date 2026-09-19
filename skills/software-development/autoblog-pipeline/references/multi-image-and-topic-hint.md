# Multi-image pipeline, topic hint, dan ordering — sesi 2026-08-25

Pelajaran tambahan setelah SKILL.md awal ditulis. Semua sudah diuji live di
`~/ai-browser/bot.py` + `~/autoblog-blog` (https://ngopigame-blog.vercel.app).

## Topik spesifik via argumen `/newarticle <topik>`

User minta bisa nentuin topik sendiri: `/newarticle Persib Bandung` harus nulis
artikel TENTANG Persib, bukan topik default config.

Implementasi di `cmd_newarticle`:
- `arg = " ".join(ctx.args).strip()` → `run_new_article_pipeline(hint=arg)`
- Di `run_new_article_pipeline(hint="")`: `query = hint if hint else cfg["blog_topic"]`
- Kalau hint ada: `topic["title"] = hint[:80]` — override judul topik biar AI
  nulis tentang topik itu, bukan judul berita pertama hasil search.
- Bot reply progress: "📌 Topik: *Persib Bandung*"

Test live: `/newarticle Persib Bandung` → judul artikel
"Persib Bandung: Ambisi Besar Maung Bandung di Musim 2026", 3 sumber dibaca,
hero + 3 inline image dari Antara News, provider `9router ✓ [FREE]`.

## Urutan feed: terbaru di ATAS (bukan append)

Bug: `posts.append(...)` menaruh artikel baru di index terakhir → feed nampilin
artikel terlama duluan. Fix:
- `posts.insert(0, {...})` di `publish_to_blog`
- Untuk artikel lama yang sudah terlanjur append: `posts.reverse()` sekali,
  tulis ulang posts.json, push.

## Multi-image: hero + inline + fallback Bing

Alur lengkap di pipeline:
1. **Hero**: `extract_og_image(url)` — cuma ambil dari sumber pertama.
2. **Inline**: `extract_article_images(url, limit=4)` (fungsi baru di engine.py):
   - pakai `smart_fetch` + BeautifulSoup
   - ambil og:image dulu, lalu `<img>` dalam article/main/body
   - filter: skip `.svg`, `logo`, `icon`, `avatar`, `sprite`, `spacer`, `blank`,
     `pixel`, `banner`, `static.`
   - handle `data-src`/`data-original` (lazy-load), urljoin relative
3. **Fallback**: kalau hero+inline kosong → `_search_images(title)`:
   - scrape Bing image search: `https://www.bing.com/images/search?q=<q>`
   - regex `murl&quot;:&quot;(https?[^&"]+?)&quot;`
   - ⚠️ DuckDuckGo image API (`duckduckgo.com/i.js`) → **403 Forbidden**, jangan dipakai
   - filter sama: svg/logo/icon/banner/static
4. **Download**: `_download_multiple_images(urls, blog_dir, slug, limit=3)`:
   - save `images/<slug>_f<i>.<ext>`, skip < 5KB, pakai UA header
5. **Inject**: `_inject_images(content, paths)`:
   - split content jadi blok HTML (`(?=</?(?:p|h2|h3|ul|ol|blockquote|figure)[^>]*>)`)
   - sisipkan `<figure>` di posisi fraksi (i+1)/(N+1) dari total blok
   - figure: img rounded 14px + figcaption "Ilustrasi" (mono, fg-faint)

## Notifikasi Telegram: jangan kirim HTML mentah

Bug: `body += esc(article['html'][:200])` → notifikasi nampilin `&lt;p&gt;...`
Fix: `esc(_clean_excerpt(article.get("html",""), 180))` — tag-strip dulu.

## Debug penting

- Sandbox `execute_code` TIDAK punya bs4/engine — import engine/bot dari sandbox
  gagal `ModuleNotFoundError: bs4`. Jalankan lewat terminal (venv bot) atau
  copy fungsi (misal `_inject_images`, `_article_template`) dengan `exec` segmen
  source dari bot.py — bukan `from bot import ...`.
- `exec(src[start:end], ns)` untuk ekstrak satu fungsi dari bot.py tanpa
  menjalankan seluruh modul (menghindari import bs4 di engine).
- PM2 daemon bisa ke-reset (daftar proses kosong) — `pm2 start ... --name X`
  ulang + `pm2 save`. Jangan `pm2 delete <nama>` kalau ada 2 proses nama sama
  (hapus dua-duanya!) — pakai `pm2 delete <id>` spesifik.

## Ganti tema blog (topik konten)

- `~/autoblog/config.json` → `blog_topic` (misal "sepak bola dan berita olahraga")
- `~/autoblog-blog/index.html` → title/tagline/hero text
- fallback default di `bot.py` `run_new_article_pipeline` (cfg dict lokal)
- push → Vercel redeploy
