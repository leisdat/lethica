# 2-Pass Fact Extraction & Source Scoring — Sesi 2026-08-25

## Mengapa: review user membongkar kelemahan kritis

User review (setelah 3+ artikel live) menemukan pola berulang:
- **Judul spesifik → isi generik**: "Jadwal Lengkap + Prediksi" tapi tidak ada jadwal/skor
- **Kalimat kosong**: "dunia sepak bola penuh drama", "kabar gembira terus berdatangan"
- **Tidak ada data konkret**: tidak ada nama pemain, klub, skor, tanggal, sumber
- **Evergreen bukan news**: artikel yang bertanggal hari ini bisa dipublikasikan kapan saja
- **Indikasi AI filler**: bagian transfer hanya bilang "Beberapa nama besar dikabarkan..." tanpa nama

Root cause: prompt single-shot ("tulis artikel tentang X") → AI mengisi dari pengetahuan umum,
bukan dari data yang di-fetch dari sumber berita.

## Fix: 2-pass pipeline (terbukti live)

### Pass 1: `_extract_facts(context, topic_title)` → DAFTAR FAKTA TERVERIFIKASI

Prompt: AI sebagai ekstraktor berita, tugas:
- "Keluarkan daftar fakta: [FAKTA] <siapa/klub/skor/kapan/transfer> + Sumber: <domain>"
- HANYA fakta yang benar-benar tertulis di konteks — JANGAN tambahkan pengetahuan sendiri
- Kalau konteks cuma bahasan umum tanpa data → output: `TIDAK ADA FAKTA TERVERIFIKASI`
- Range 5–15 fakta
- Fokus: hasil pertandingan, transfer pemain (pemain→klub, nilai), jadwal, cedera, klasemen, pernyataan resmi pelatih/pemain

### Pass 2: `write_article` → ARTIKEL BERITA dari fakta SAJA

Setelah pass 1, prompt penulisan menerima `facts` (bukan raw context):
- "Tulis artikel BERITA TERKINI berdasarkan FAKTA TERVERIFIKASI. Ini bukan artikel evergreen."
- Setiap paragraf WAJIB berisi fakta; kalimat generik dilarang eksplisit (disebutkan contohnya)
- Struktur: pembuka 1-2 kalimat → ## Berita Utama Hari Ini (tiap item + "(Sumber: domain)")
  → ## Transfer Terbaru → ## Jadwal (wajib `<table>`) → penutup
- **Judul WAJIB akurat**: jangan pakai "Jadwal Lengkap"/"Prediksi" kalau data tidak ada
- Kalau fakta = "TIDAK ADA FAKTA TERVERIFIKASI" → judul jujur ("Belum Ada Update...")
  + html singkat + saran pantau sumber resmi. JANGAN paksakan artikel.
- Setiap fakta WAJIB ada "(Sumber: <domain>)" — verifiable, bukan filler.

### Test live: "hasil liga inggris tadi malam" → hasil:

```
Judul: Hasil Liga Inggris Tadi Malam: Arsenal Puncaki Klasemen, Chelsea Ditahan...
Berita Utama:
- Arsenal Bantai Nottingham Forest 3-0, Kembali ke Puncak (skor, stadion, tanggal)
- Chelsea gagal tiga poin setelah kebobolan injury time
- Bournemouth ke posisi 4 besar
- Setiap paragraf ada (Sumber: liputan6.com)
- Zero kalimat generik
```

### Test live: "Premier League jadwal 26 Agustus 2026" → hasil:

```
Judul: Informasi Terkini Seputar Premier League 26 Agustus 2026
Isi: "Sayangnya, data spesifik mengenai jadwal pertandingan Premier League
untuk tanggal 26 Agustus 2026 belum tersedia dari sumber yang dirujuk..."
+ saran pantau sumber resmi
```

## Source selection: jangan ambil top-3 search mentah

DuckDuckGo top results sering homepage/listing (detik.com/sepakbola) tanpa data artikel.
Scoring filter:

```python
def score(r):
    u = r.get("href",""); s = 0
    if "/" in u.replace("https://","").replace("http://","")[15:]:
        s += 2  # ada path setelah domain (bukan homepage)
    for kw in ("berita","news","detail","artikel","post","/p/","2026"):
        if kw in u.lower(): s += 1
    for kw in ("hasil","skor","transfer","resmi","menang","kalah","imbang"):
        if kw in r.get("title","").lower(): s += 1
    return s
results.sort(key=score, reverse=True)
sources = results[:3]
```

Juga: set `topic["title"] = hint` kalau user kasih argumen spesifik — jangan pakai
judul hasil search pertama sebagai judul topik.

## Catatan: prompt harus menyebut tanggal hari ini eksplisit

Kalau tidak, AI kadang bilang "besok" atau "pertandingan tadi malam" tanpa tanggal.
Tambahkan di prompt: `TANGGAL HARI INI: <tanggal>` (dinamis, diisi datetime.now()).