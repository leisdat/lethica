# Environment

## Purpose
Mengelola runtime, konfigurasi, dan variabel lingkungan.

## Rules

- Gunakan environment variables untuk secret, bukan hardcode.
- Pisahkan config dev / staging / production.
- Jangan commit file .env berisi credential.
- Verifikasi variabel tersedia sebelum dipakai.
- Dokumentasikan variabel wajib (contoh .env.example).

## Workflow

inspect current env
→ identify required vars
→ set / load (env file / export)
→ verify
→ run dependent process

## Common

- export VAR=value
- load dari .env
- activate virtualenv / conda
- set PATH tambahan

## Avoid

- hardcode API key di source
- mengubah global env tanpa catatan
- lupa unset var eksperimental
- commit secret ke repo
