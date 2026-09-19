# Extraction

## Purpose

Ekstraksi string.

## Kapan Digunakan

- Perlu memeriksa/mengevaluasi dalam **Localization / i18n**.
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

- Scan code.
- Key scheme.
- No leak.
- Update.
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

Localization / i18n
