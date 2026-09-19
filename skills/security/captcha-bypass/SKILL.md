---
name: captcha-bypass
description: "OCR, token replay, & anti-captcha buat test captcha sendiri."
---

# Captcha Bypass

Teknik bypass captcha untuk testing keamanan sistem sendiri. Empat kategori: OCR, token replay, audio solve, API service.

## Trigger
- "captcha susah di-script"
- "mentok di Turnstile / reCAPTCHA / hCaptcha"
- "test captcha di sistem sendiri"
- "auto-register faucet"

## Kategori Captcha

| Jenis | Proteksi | Teknik Bypass |
|-------|----------|---------------|
| **Image text** (teks acak gambar) | Rendah | OCR (Tesseract, ddddocr) |
| **Image math** (3+5=?) | Rendah | OCR + kalkulasi |
| **Image object** (pilih mobil) | Sedang | ML classifier |
| **Token/CAPTCHA berbasis session** | Rendah-Sedang | Replay token, CSRF analysis |
| **reCAPTCHA v2** (pilih gambar) | Tinggi | Anti-captcha service, browser emulation |
| **reCAPTCHA v3** (score-based) | Tinggi | Browser fingerprint, human-like behavior |
| **hCaptcha** | Tinggi | Anti-captcha service |
| **Cloudflare Turnstile** | Tinggi | Browser automation + token extraction |
| **Tencent Captcha** | Tinggi | Sama kayak Turnstile |
| **Audio captcha** | Sedang | Speech-to-text (Google STT, whisper) |

## Tools di HP lo

### 1. OCR — Tesseract (udah terinstall)

```bash
# Langsung dari file gambar
tesseract captcha.png stdout

# Dengan preprocessing (grayscale + threshold)
python3 -c "
from PIL import Image, ImageFilter, ImageEnhance
import pytesseract

img = Image.open('captcha.png')
# Grayscale + threshold
img = img.convert('L')
img = img.point(lambda x: 0 if x < 140 else 255)
# OCR
print(pytesseract.image_to_string(img, config='--psm 7 digits'))
"
```

### 2. Token Replay (paling gampang, sering tembus)

Banyak captcha cuma generate token sekali, tapi gak nge-validasi token itu udah dipakai:

```bash
# 1. Buka halaman, ambil captcha token
curl -s "https://site.com/captcha" -c cookies.txt | grep -oP 'captcha_token[^<]+'

# 2. Kirim form PAKE token yang sama (bisa di-replay berkali-kali)
curl -s "https://site.com/submit" -b cookies.txt \
  -d "captcha_token=$TOKEN&data=..."

# 3. Kalau server gak invalidate token setelah dipakai → tembus
```

### 3. Audio Captcha → Speech-to-Text

```bash
# Download audio captcha
curl -s "https://site.com/audio.mp3" -o captcha.mp3

# Convert ke text pake whisper (butuh model)
whisper captcha.mp3 --model tiny 2>/dev/null | grep -oP '[0-9]+'
```

### 4. Anti-Captcha API Service (buat captcha berat)

Untuk reCAPTCHA/hCaptcha/Turnstile — butuh service berbayar:
- **2captcha** (~$0.5-2 per 1000 solve)
- **AntiCaptcha** (sama)
- **CapSolver** (paling murah untuk Turnstile)

```bash
# Contoh: 2captcha API
curl -s "https://2captcha.com/res.php?key=API_KEY&action=getbalance"
```

## Skrip: captcha_solve.py

```python
#!/usr/bin/env python3
"""
captcha_solve.py — solve captcha dari file gambar.
Support: image text, token replay, audio.
"""
import sys, os, subprocess, json
from PIL import Image, ImageFilter, ImageEnhance

# PyTesseract (optional)
try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

def preprocess(img_path):
    """Preprocess image untuk OCR: grayscale + threshold + noise removal."""
    img = Image.open(img_path)
    # Convert ke grayscale
    img = img.convert('L')
    # Threshold (adjust 140 sesuai kebutuhan)
    img = img.point(lambda x: 0 if x < 140 else 255)
    # Resize 2x untuk OCR lebih akurat
    w, h = img.size
    img = img.resize((w*2, h*2), Image.LANCZOS)
    return img

def solve_tesseract(img_path, digits_only=False):
    """Solve captcha pake Tesseract OCR."""
    if not HAS_TESSERACT:
        return subprocess.run(
            ["tesseract", img_path, "stdout"],
            capture_output=True, text=True
        ).stdout.strip()
    img = preprocess(img_path)
    config = '--psm 7 -c tessedit_char_whitelist=0123456789' if digits_only else '--psm 7'
    return pytesseract.image_to_string(img, config=config).strip()

def solve_token_replay(captcha_token, endpoint, form_data, cookies):
    """Coba replay captcha token yang sama berkali-kali."""
    import urllib.request
    data = form_data.copy()
    data['captcha_token'] = captcha_token
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(endpoint, data=body)
    req.add_header('Cookie', cookies)
    with urllib.request.urlopen(req) as r:
        return r.read().decode()

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: captcha_solve.py <image.png> [--digits]')
        sys.exit(1)
    digits = '--digits' in sys.argv
    result = solve_tesseract(sys.argv[1], digits)
    print(f'Captcha: {result}')
```

## Catatan Kritis

1. **Token replay** adalah bypass paling umum — banyak dev lupa invalidate token setelah dipakai. Selalu coba ini dulu sebelum OCR.
2. **reCAPTCHA v3** gak punya challenge visual — dia kasih score berdasarkan behavior. Bypass = tiru human behavior (mouse movement, delay, scroll).
3. **Cloudflare Turnstile** = versi Cloudflare dari reCAPTCHA. Bypass butuh browser real + token extraction.
4. **Anti-captcha service** = jalan terakhir buat captcha berat. Bayar per solve (~$0.001-0.01).
5. **Rate limit + captcha** sering dipasang barengan. Bypass rate limit dulu, baru captcha.

## Hasil Tuning OCR (Tesseract 5.5 di Termux, 2026-09-02)

Test pakai gambar generate sendiri (PIL):

| Noise | Expected | OCR Result | Config Optimal |
|-------|----------|-----------|----------------|
| 0.0 (bersih) | TEST1 | TEST1 ✅ | threshold 140, psm 7 |
| 0.5 (sedang) | 12345 | 12345 ✅ | **threshold 100**, psm 7 |
| 0.7 (tinggi) | K7M2P | K72P ⚠️ | threshold 100, psm 7 |

**Config optimal:**
- `--psm 7` (single line) — psm 8/13 hasil kacau
- **threshold 100** (bukan 140) untuk captcha ber-noise
- Resize 3x, bukan 2x
- Angka campur huruf (7 vs M, 0 vs O) jadi batas Tesseract — butuh model ML (ddddocr) untuk akurasi lebih

**Catatan:** captcha eksternal (phpcaptcha.org, capskip) di-block Cloudflare dari Termux — test lokal dengan generate sendiri lebih reliable buat benchmark.

## File Referensi

- Script: `~/.hermes/tmp/captcha_solve.py`
- Test image: `~/.hermes/tmp/captcha_test.png`
