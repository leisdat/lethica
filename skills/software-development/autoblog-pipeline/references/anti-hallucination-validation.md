# Anti-Hallucination Layer (Lapis 3) — 2026-08-26

## Mengapa lapis 3 dibutuhkan: 2-pass saja MASIH bisa ngarang

Review user ke-3 membuktikan: setelah 2-pass fact extraction, saat `fetch_page`
mengembalikan **teks kosong** (anti-bot / rate-limit, contoh liputan6.com), context = ""
→ AI tetap menulis artikel dengan skor karangan ("Arsenal 3-0", "MU 2-1") dari
pengetahuan umum, karena prompt pass 2 tetap jalan walau fakta kosong.

Pola user review yang berulang (3 artikel): **judul spesifik → isi generik tanpa data**.
Fix bertingkat di bawah ini terbukti menutupnya.

## Fix yang terbukti (urut eksekusi di pipeline)

### 1. Short-circuit `_extract_facts` saat context kosong — jangan panggil AI

```python
if not context or len(context.strip()) < 200:
    return "TIDAK ADA FAKTA TERVERIFIKASI (konteks sumber kosong — anti-bot)"
```

### 2. ABORT di `write_article` kalau fakta = "TIDAK ADA FAKTA"

```python
if "TIDAK ADA FAKTA" in facts.upper():
    raise ValueError("Tidak ada data terverifikasi dari sumber untuk topik ini...")
```

User lebih suka pipeline GAGAL jujur daripada publish konten palsu.
Handler bot menangkap ValueError dan balas ke Telegram dengan pesan abort.

### 3. Filter source di pipeline — skip teks pendek

```python
txt = page.get("text", "") or ""
if txt and len(txt.strip()) > 300:
    contexts.append(...)
```

### 4. `_validate_scores(article_html, facts)` — anti-hallucination final

Setelah artikel jadi, scan skor pola `\d+-\d+` di HTML; yang tidak ada di string
facts → ganti dengan `**hasil belum dikonfirmasi**`:

```python
scores = re.findall(r"\b\d{1,2}\s*[-–:]\s*\d{1,2}\b", text)
for s in scores:
    if s.replace(" ", "") not in facts.replace(" ", ""):
        cleaned = re.sub(r"\b" + re.escape(s) + r"\b",
                         "**hasil belum dikonfirmasi**", cleaned)
```

### 5. Prompt pass 2 diperkuat

- Aturan eksplisit: "HANYA TULIS ANGKA/SKOR YANG ADA DI FAKTA. JANGAN mengarang
  '2-1' kalau tidak ada di fakta."
- "VALIDASI DIRI: baca ulang artikelmu, kalau ada angka yang tidak ada di FAKTA →
  HAPUS dan ganti 'belum dikonfirmasi'."
- Attach `art["_facts"] = facts` supaya `_validate_scores` punya sumber pembanding.

## Test bukti

- `hasil liga inggris tadi malam` (detik.com kebaca) → skor 3-0, 2-2, 2-1
  **terverifikasi dari fakta**, lolos `_validate_scores` (tidak ada yang dihapus).
- `turnamen catur merdeka` (sumber anti-bot) → **ABORT jujur**, tidak publish.

## Pipeline news yang benar (kesimpulan)

```
keyword → filter source (skor URL: path + kata kunci hasil/skor/transfer)
→ fetch (skip <300 chars) → pass 1 ekstrak fakta (short-circuit kosong)
→ ABORT kalau tanpa fakta → pass 2 tulis dari fakta
→ _validate_scores (hapus angka palsu) → publish
```

Kualitas = sebaik sumber yang bisa di-fetch. **Lebih baik abort daripada ngarang.**

## Gotcha tambahan

- Source selection: DuckDuckGo top-3 mentah sering homepage/listing (detik.com/sepakbola)
  tanpa data. Scoring filter: URL punya path setelah domain (+2), mengandung
  berita/news/detail/artikel (+1), judul mengandung hasil/skor/transfer/resmi (+1).
- Kalau user kasih argumen spesifik (`/newarticle Persib Bandung`), set
  `topic["title"] = hint` — jangan pakai judul hasil search pertama.
- Prompt harus menyebut `TANGGAL HARI INI: <tanggal>` dinamis, biar AI tidak
  bilang "besok"/"tadi malam" tanpa tanggal.
