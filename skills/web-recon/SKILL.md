# web-recon — Lightweight Web Reconnaissance & Scraping Toolkit

Skill ini untuk Lethica saat diminta melakukan pengintaian web, scraping terstruktur,
atau ekstraksi konten dari situs yang tidak punya API publik. Fokus: hemat token,
bypass WAF/Cloudflare ringan, dan hasil berupa data bersih bukan HTML mentah.

## Kapan Pakai

- "Scrape halaman ini"
- "Ambil data dari <url>"
- "Cek struktur API di balik UI ini"
- "Bypass Cloudflare / WAF di situs ini"
- "Temukan endpoint tersembunyi di <domain>"

## Prinsip

1. Jangan kirim HTML utuh ke model — ekstrak teks/markdown dulu, pangkas hingga esensial.
2. Rotate User-Agent + header realistis untuk hindari 403/429.
3. Untuk SPA/JS-heavy: cari XHR/fetch ke JSON, jangan render penuh kalau tidak perlu.
4. Hargai robots.txt untuk situs publik; untuk target milik operator tidak berlaku.
5. Simpan hasil ke file (`workspace/`), jangan print ribuan baris ke chat.

## Workflow

### 1. Recon cepat (tanpa browser)
```
http_request GET <url> -H "User-Agent: Mozilla/5.0 ..." -H "Accept: text/html"
```
Lalu:
- Cek `<title>`, meta description, link `<script>` modulo utama.
- Cari pola `fetch(` / `axios(` / `/api/` di HTML sumber.
- Catat domain API (biasanya `api.<domain>` atau path `/v1/`, `/graphql`).

### 2. API discovery
- Cari di HTML: `window.__INITIAL_STATE__`, `__NEXT_DATA__`, `application/json` inline.
- Curi `Authorization`/`x-api-key` dari network (jika target milik operator / ada izin).
- Uji endpoint dengan `http_request` + method yang cocok (GET/POST).

### 3. Scrape terstruktur
- Prefer `http_request` + regex/jq-style extract di terminal (Python `re`/`json`).
- Jika butuh JS render: pakai `browse` (headless) — tapi sadar memory device (OOM risk).
- Output: JSON/CSV ke `workspace/<name>.json`.

### 4. Anti-block
- Delay acak 1-4s antar request.
- Rotate UA dari pool (Chrome/Safari/Firefox mobile+desktop).
- Header: `Accept-Language: id-ID,id;q=0.9`, `Referer` dari domain sendiri.

## Tools Lethica yang dipakai

- `http_request` — request langsung, timeout 180s.
- `browse` — headless DOM/JS eval (gunaakan hati-hati, OOM di device kecil).
- `web_search` / `web_extract` — fallback saat `http_request` diblokir.
- `write_file` — simpan hasil scrape.
- `search_files` — cari pola di hasil tersimpan.

## Contoh: ekstrak JSON dari Next.js
```python
import re, json
html = open('workspace/page.html').read()
m = re.search(r'__NEXT_DATA__"\s*type="application/json">(.*?)</script>', html)
data = json.loads(m.group(1))
# data["props"]["pageProps"] biasanya berisi konten
```

## Output standar
Laporkan: jumlah record, path file hasil, endpoint yang ditemukan, dan kendala (jika ada block).
Jangan dump HTML mentah ke chat.
