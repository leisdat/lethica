# Warroom

## Purpose

Koordinasi respon.

## Kapan Digunakan

- Jalankan operasi konkret di **Incident Management**.
- Setelah pra-syarat valid.
- Capai state akhir terverifikasi.

## Workflow

Prepare
→ Execute
→ Capture Output
→ Verify
→ Cleanup

## Rules

- Channel.
- Lead.
- Roles.
- Log.
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

Incident Management
