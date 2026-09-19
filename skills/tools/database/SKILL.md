# Database

## Purpose
Operasi database: query, schema, migration, maintenance.

## Rules

- Pahami schema sebelum query.
- Validasi input parameter (hindari injection).
- Gunakan parameterized query.
- Jangan jalankan DROP / DELETE tanpa WHERE yang jelas.
- Backup sebelum operasi destruktif.
- Jangan expose credential di log / output.

## Workflow

connect
→ inspect schema
→ compose query (parameterized)
→ execute
→ verify affected rows
→ close

## Common

- SELECT: baca data
- INSERT / UPDATE / DELETE: modifikasi
- CREATE / ALTER: schema
- migration: perubahan terkontrol

## Avoid

- string concatenation untuk query
- query tanpa limit pada tabel besar
- operasi destruktif tanpa backup
- commit di luar transaction saat tidak aman
