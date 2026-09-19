# Template

## Purpose

Template pesan reusable.

## Kapan Digunakan

- Kelola siklus hidup artefak di **Communication**.
- Tambah/perbarui/hapus aman.
- Jaga konsistensi & dependensi.

## Workflow

Validate Input
→ Apply Change
→ Verify State
→ Update Index
→ Notify

## Rules

- Variable aman.
- Escaping.
- Localization.
- Preview.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Failure Handling

- Gagal: baca error, root cause, perbaiki.
- Retry hanya aman & terbatas.
- Butuh otorisasi: henti & eskalasi.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Communication
