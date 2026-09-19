# Vision tool can't read the user's screenshot (Termux local fs)

## Symptom
User kirim screenshot (Telegram image). `vision_analyze` balas:
- "It looks like you haven't attached or provided an image" — padahal file ADA di fs
- atau analysis kosong/"no image" padahal path valid

Lokasi file: `~/.hermes/cache/images/img_<hash>.jpg` (konfirmasi dulu: `ls -la` di terminal).

## Root cause (terverifikasi 2026-09-08)
1. **Hermes vision tool jalan di sandbox TANPA akses ke fs lokal Termux** — path `/data/data/com.termux/...` gak bisa dibaca tool, jadi dianggap "no image".
2. **Gagal parse progressive JPEG** — screenshot dark-theme dari Chrome Android sering progressive JPEG; vision tool return kosong tanpa error jelas.

## Recovery path (yang berhasil)
1. **Re-encode dulu** (beresin progressive JPEG):
   ```bash
   # ffmpeg
   ffmpeg -i in.jpg -q:v 2 out.jpg
   # atau PIL
   python3 -c "from PIL import Image; Image.open('in.jpg').convert('RGB').save('out.jpg', quality=92)"
   ```
   Ini yang bikin vision akhirnya bisa parse (tapi tetap gak bisa akses fs lokal — lihat #3).
2. **OCR dengan tesseract** (sering sudah terinstall di Termux: `which tesseract`):
   ```bash
   tesseract out.jpg stdout
   ```
   Untuk screenshot UI dark-theme (teks putih) hasil OCR cukup buat konfirmasi state: label tombol, info episode, judul, resolusi. Bukan sempurna tapi cukup buat verifikasi cepat.
3. **Ground truth = kode, bukan OCR**. Screenshot cuma konfirmasi rendered state. Untuk memastikan perubahan beneran live, cross-check dengan:
   - `search_files` / `read_file` ke source file (mis. `watch.js`)
   - `curl http://127.0.0.1:<port>/js/views/<file>.js | wc -c` == byte file di disk (cek server serve versi baru)

## Caveat
- OCR error di image low-res/blur — jangan percaya buta, selalu corroborate dengan served-file check (`curl` byte-size match) sebelum claim "fitur live".
- Jangan buang waktu coba ulang `vision_analyze` berkali-kali pada file lokal Termux — sandbox gak akan bisa akses fs. Langsung ke tesseract + curl check.
