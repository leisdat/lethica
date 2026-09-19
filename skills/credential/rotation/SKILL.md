# Rotation

## Purpose

Rotasi secret berkala.

## Kapan Digunakan

- Kelola siklus hidup artefak di **Credential / Secret Management**.
- Tambah/perbarui/hapus aman.
- Jaga konsistensi & dependensi.

## Workflow

Validate Input
→ Apply Change
→ Verify State
→ Update Index
→ Notify

## Rules

- Jadwal.
- Zero-downtime.
- Verify pasca-rotasi.
- Alert gagal.
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

Credential / Secret Management
