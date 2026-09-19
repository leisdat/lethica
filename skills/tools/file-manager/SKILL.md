# File Manager

## Purpose
Manipulasi file dan direktori dengan aman.

## Operations

- create file/directory
- read file
- write file (overwrite)
- edit file (targeted replace)
- move / rename
- copy
- delete
- list / search
- inspect metadata

## Rules

- Gunakan path absolut atau relatif yang jelas.
- Cek apakah file tujuan sudah ada sebelum overwrite.
- Untuk edit, gunakan replace targeted, bukan rewrite seluruh file.
- Jangan hapus file di luar scope project tanpa alasan.
- Jangan simpan secret ke file plaintext yang ter-commit.
- Verifikasi hasil tulis (baca kembali / cek ukuran).

## Safe Workflow

inspect path
→ tentukan operasi
→ execute
→ verify (read / list)

## Avoid

- rm -rf tanpa target jelas
- wildcard destruktif
- menimpa file penting tanpa backup
- membuat file di lokasi tidak relevan
