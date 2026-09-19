# Repair

## Purpose

Perbaikan otomatis.

## Kapan Digunakan

- Jalankan operasi konkret di **Self-Healing**.
- Setelah pra-syarat valid.
- Capai state akhir terverifikasi.

## Workflow

Prepare
→ Execute
→ Capture Output
→ Verify
→ Cleanup

## Rules

- Safe script.
- Backup pre.
- Idempoten.
- Scope kecil.
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

Self-Healing
