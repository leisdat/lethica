# Validate

## Purpose

Validasi integritas.

## Kapan Digunakan

- Perlu memeriksa/mengevaluasi sesuatu dalam domain **Data / Storage**.
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

- Constraint & type.
- Outlier detection.
- Quarantine invalid.
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

Data / Storage
