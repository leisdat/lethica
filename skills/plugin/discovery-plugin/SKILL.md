# Discovery Plugin

## Purpose

Menemukan plugin tersedia.

## Kapan Digunakan

- Perlu memeriksa/mengevaluasi dalam **Plugin Ecosystem**.
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

- Scan dir.
- Manifest.
- Enable/disable.
- Index.
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

Plugin Ecosystem
