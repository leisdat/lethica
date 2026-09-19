# Conflict Resolution

## Purpose

Menyelesaikan benturan antar agent.

## Kapan Digunakan

- Jalankan operasi konkret di **Multi-Agent Collaboration**.
- Setelah pra-syarat valid.
- Capai state akhir terverifikasi.

## Workflow

Prepare
→ Execute
→ Capture Output
→ Verify
→ Cleanup

## Rules

- Deteksi konflik eksplisit.
- Strategi: last-write / merge / arbiter.
- Audit hasil resolusi.
- Escalate bila ambigu.
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

Multi-Agent Collaboration
