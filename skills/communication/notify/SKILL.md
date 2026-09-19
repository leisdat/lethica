# Notify

## Purpose

Notifikasi event.

## Kapan Digunakan

- Jalankan operasi konkret di **Communication**.
- Setelah pra-syarat valid.
- Capai state akhir terverifikasi.

## Workflow

Prepare
→ Execute
→ Capture Output
→ Verify
→ Cleanup

## Rules

- Filter relevan.
- Batching.
- Severity.
- Quiet hours.
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
