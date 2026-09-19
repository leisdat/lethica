# Correction

## Purpose

Memperbaiki kesalahan langsung.

## Kapan Digunakan

- Perlu menjalankan operasi konkret dalam domain **Learning / Improvement**.
- Setelah validasi pra-syarat terpenuhi.
- Untuk mencapai state akhir yang terverifikasi.

## Workflow

Prepare
→ Execute
→ Capture Output
→ Verify
→ Cleanup

## Rules

- Deteksi cepat.
- Audit trail.
- Cegah recurrence.
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

Learning / Improvement
