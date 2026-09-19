# Package Manager

## Purpose
Mengelola dependency dan tooling proyek.

## Rules

- Cek dependency yang sudah ada sebelum install baru.
- Pertimbangkan bundle size / security / maintenance.
- Lock version bila proyek menggunakannya.
- Jangan install package tidak perlu.
- Update dengan hati-hati (breaking change).

## Workflow

inspect manifest (package.json / requirements.txt / pyproject / Cargo.toml)
→ identify need
→ add / remove / update
→ verify install
→ run build / test

## Common

- install: tambah dependency
- remove: hapus yang tidak dipakai
- update: naik versi
- audit: cek kerentanan

## Avoid

- install package dari sumber tidak dikenal
- version wildcard ekstrem tanpa alasan
- menambah dependency untuk fitur trivial
