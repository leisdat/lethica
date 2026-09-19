# Invalidate

## Purpose

Menghapus entri cache/state.

## Kapan Digunakan

- Perlu memeriksa/mengevaluasi sesuatu dalam domain **State / Cache**.
- Sebelum menyatakan komponen aman/benar/selesai.
- Untuk menemukan anomali, defect, atau deviation dari standar.

## Workflow

Define Scope
→ Collect Evidence
→ Compare to Standard
→ Classify Findings
→ Report
→ Recommend

## Rules

- Invalidate saat source berubah.
- Batch invalidate via tag.
- Jangan leak reference.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Output Format

Gunakan severity: CRITICAL / HIGH / MEDIUM / LOW / INFO.
Untuk tiap temuan sertakan:
- lokasi
- masalah
- dampak
- rekomendasi perbaikan

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

State / Cache
