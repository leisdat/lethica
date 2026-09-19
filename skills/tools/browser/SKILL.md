# Browser

## Purpose
Akses web, dokumentasi, dan halaman yang butuh rendering / interaksi.

## When To Use

- Buka dokumentasi resmi
- Cek halaman yang tidak bisa di-fetch statis
- Login / session yang butuh cookie
- Inspect DOM / JS-rendered content
- Web research

## Rules

- Prefer fetch statis bila cukup (lebih hemat).
- Jangan masukkan credential ke form login tanpa instruksi user.
- Jangan menjalankan script halaman asing sembarangan.
- Catat URL sumber untuk referensi.
- Tutup / bersihkan session bila tidak dipakai.

## Workflow

navigate
→ wait load
→ inspect (DOM / text)
→ extract
→ verify

## Avoid

- screenshot berlebihan bila tidak perlu
- infinite scroll tanpa batas
- mengikuti redirect ke situs tidak dikenal
