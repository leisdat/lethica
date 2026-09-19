# Update

## Purpose

Memperbarui isi skill.

## Kapan Digunakan

- Perlu mengelola siklus hidup artefak dalam **Skill Manager**.
- Saat menambah/memperbarui/menghapus komponen secara aman.
- Untuk menjaga konsistensi & dependensi.

## Workflow

Validate Input
→ Apply Change
→ Verify State
→ Update Index
→ Notify

## Rules

- Backup versi lama.
- Diff sebelum overwrite.
- Bump versi.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Failure Handling

- Jika gagal: baca error, identifikasi root cause, perbaiki input/strategi.
- Retry hanya jika aman & terbatas.
- Jika butuh otorisasi: henti & eskalasi, jangan lanjut diam-diam.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Skill Manager
