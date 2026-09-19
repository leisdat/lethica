# Lifecycle

## Purpose

Siklus hidup plugin.

## Kapan Digunakan

- Kelola siklus hidup artefak di **Plugin Ecosystem**.
- Tambah/perbarui/hapus aman.
- Jaga konsistensi & dependensi.

## Workflow

Validate Input
→ Apply Change
→ Verify State
→ Update Index
→ Notify

## Rules

- Install→Enable→Run→Disable→Uninstall.
- Backup.
- Rollback.
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

Plugin Ecosystem
