# Rollback Change

## Purpose

Pengembalian perubahan.

## Kapan Digunakan

- Kelola siklus hidup artefak di **Change Management**.
- Tambah/perbarui/hapus aman.
- Jaga konsistensi & dependensi.

## Workflow

Validate Input
→ Apply Change
→ Verify State
→ Update Index
→ Notify

## Rules

- Snapshot pre.
- One-click.
- Verify.
- Cleanup.
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

Change Management
