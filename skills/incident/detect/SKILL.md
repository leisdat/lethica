# Detect

## Purpose

Mendeteksi insiden.

## Kapan Digunakan

- Perlu memeriksa/mengevaluasi dalam **Incident Management**.
- Sebelum nyatakan benar/aman/selesai.
- Temukan anomali/deviasi.

## Workflow

Define Scope
→ Collect Evidence
→ Compare
→ Classify
→ Report
→ Recommend

## Rules

- Alert rules.
- Anomaly.
- Correlate.
- De-dupe.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Output Format

Severity: CRITICAL/HIGH/MEDIUM/LOW/INFO.
Tiap temuan: lokasi, masalah, dampak, rekomendasi.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Incident Management
