# Audit Secret

## Purpose

Pencatatan penggunaan secret.

## Kapan Digunakan

- Perlu memeriksa/mengevaluasi dalam **Credential / Secret Management**.
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

- Siapa/kapan/untuk-apa.
- Immutable.
- Alert anomali.
- Retensi.
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

Credential / Secret Management
