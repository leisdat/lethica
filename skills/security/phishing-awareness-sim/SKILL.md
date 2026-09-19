---
name: phishing-awareness-sim
description: "Use when building/auditing phishing simulation training."
version: 1.0.0
author: Farul (lingxudr)
license: MIT
metadata:
  hermes:
    tags: [security, phishing, awareness, simulation, audit, training, red-team]
    related_skills: [godmode]
---

## When to Use

Use when user minta bikin simulasi phishing **edukasi** (training awareness), audit keamanan tool simulasi, atau verifikasi bahwa file HTML tidak bisa dipakai buat credential harvesting. JANGAN pakai untuk membangun phishing nyata.

# Phishing Awareness Simulation — Build + Audit

Membangun tool **edukasi anti-phishing** (bukan phising beneran) + audit keamanannya. Dikembangkan & terverifikasi sebagai "PhishLab v2" (2026-08-29).

## Batas keamanan WAJIB (jangan pernah dilewati)

1. **Zero network** — tidak ada fetch/XHR/WebSocket/SSE/sendBeacon/`new Image()`/iframe/form-action/script src.
2. **Zero third-party** — satu file self-contained; tanpa CDN, font eksternal, analytics, pixel.
3. **Zero credential persistence** — input cuma buat validasi non-empty, dibuang; JANGAN simpan email/password/userAgent/IP. Password tak pernah masuk object/localStorage/URL/parameter.
4. **Brand fiktif** — jangan pakai branding layanan nyata (Gmail/Google/Meta/Bank). Pakai domain fiktif jelas (mis. `secureportal-verify.com`, `clouddocs-share`, `payhub-billing.com`).
5. **Export aggregate-only** — hanya total + per-scenario stat; tanpa raw session, email, id, timestamp per peserta.
6. **Disclaimer terlihat** — banner merah di ATAS landing ("NOT a real login page") + footer; jangan cuma footer.
7. **localStorage only** untuk statistik anonim: `{id, timestamp, scenario, difficulty, timeToClick}`.

## Struktur single-file yang terbukti

- 5 phase div: `phasePick` (scenario picker), `phaseMail` (email client mock + decoy), `phaseLanding` (form dummy), `phaseEducation` (red flags + tips), `phaseInstructor` (dashboard per-scenario).
- Data `SCENARIOS[]`: tiap scenario = `{id, icon, title, difficulty(easy|medium|hard), type, email{...}, landing{logo,brand,title,sub,fields[],cta,footer,urlHint}, redFlags[{icon,title,desc,severity}]}`.
- Difficulty **hard** = tanpa urgency, kalem & profesional (paling sulit dikenali — nilai edukasi tinggi).
- Form: `<form>` tanpa `action` + `addEventListener('submit', e => e.preventDefault())`. `autocomplete="new-password"` di password.
- `recordSession(timeToClick)` — parameter hanya durasi; JANGAN tambah email/password.

## Regression checklist (bisa di-CI)

```bash
# 1. Zero network
grep -cE '(fetch\(|XMLHttpRequest|WebSocket|EventSource|sendBeacon|new Image\(|\.src =)' FILE.html   # =0
# 2. Zero external resource
grep -cE '(src="http|href="http|@import|@font-face|googleapis|gstatic|cdn\.)' FILE.html              # =0
# 3. Form no-action + preventDefault
grep -c 'action="' FILE.html                     # =0
grep -c 'preventDefault' FILE.html               # >=1
# 4. Password tidak dipersistenkan (cek PERSISTENCE, bukan keberadaan kata!)
grep -nE '(recordSession|saveData|sessions\.push|setItem)' FILE.html | grep -ci password             # =0
grep -cE 'function [a-zA-Z]+\([^)]*password' FILE.html                                                # =0
# 5. Email tidak dipersistenkan
sed -n '/sessions.push/,/});/p' FILE.html | grep -viE 'NOTE|//' | grep -ci email                     # =0
sed -n '/const exportObj/,/};/p' FILE.html | grep -viE '//' | grep -ci email                         # =0
# 6. Export aggregate-only
grep -A25 'const exportObj = {' FILE.html | grep -cE '^\s+sessions:'                                 # =0
# 7. Disclaimer banner
grep -cE 'sim-banner|Do not use real credentials' FILE.html                                           # >=1
# 8. Storage hanya localStorage
grep -cE '(cookies|indexedDB|sessionStorage)' FILE.html   # =0
grep -c 'localStorage' FILE.html                          # >=1
```

**PITFALL penting:** grep `'password'` / `'email'` di SELURUH file akan false-positive karena teks edukasi (red flags, tips, deskripsi scenario) memang menyebut kata itu. Selalu scope ke **persistence path** (recordSession/saveData/push/exportObj), bukan ke seluruh file.

## Audit independen (praktik yang terbukti)

1. Baca file **penuh** dulu (jangan asumsi) — semua handler, storage, export.
2. Trace: password dibaca → cuma validasi non-empty → dibuang. `emailVal` jadi dead code → hapus.
3. Network scan **exhaustive** (13 kategori): fetch/XHR/WS/SSE/beacon/Image/iframe/form-action/link/script-src/@import/url()/@font-face/meta-refresh/WebRTC/geolocation/postMessage/indexedDB/cookie.
4. Deployment: pindah localhost→static host = **tidak mengubah teknis** (zero backend/CORS/API key). Risiko yang ada cuma **abuse sosial** (orang upload & klaim jadi halaman asli) — mitigasi: banner disclaimer + form no-action.
5. Export: verifikasi field satu-satu; buktikan tak ada raw session/email/id/timestamp per peserta.
6. Verifikasi JS: `python3 -c "import re;open('x.js','w').write(re.search(r'<script>(.*?)</script>', open('f.html').read(), re.S).group(1))"` lalu `node --check x.js`. **JANGAN tulis ke /tmp** (unwritable di Termux) — pakai `~`.

## Run
```bash
cd ~ && python3 -m http.server 8080 --bind 0.0.0.0   # buka http://<IP-HP>:8080/xxx.html
```
Ambil IP HP: `python3 -c "import socket;s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));print(s.getsockname()[0]);s.close()"`.