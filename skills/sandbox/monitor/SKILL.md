# Monitor

## Purpose

Pantau proses sandbox.

## Kapan Digunakan

- Jalankan operasi konkret di **Simulation / Sandbox**.
- Setelah pra-syarat valid.
- Capai state akhir terverifikasi.

## Workflow

Prepare
→ Execute
→ Capture Output
→ Verify
→ Cleanup

## Rules

- Syscall/resource.
- Anomaly alert.
- Kill switch.
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

Simulation / Sandbox
