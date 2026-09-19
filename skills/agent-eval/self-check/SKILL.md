# Self Check

## Purpose

Pemeriksaan diri agent.

## Kapan Digunakan

- Perlu memeriksa/mengevaluasi dalam **Agent Self-Evaluation**.
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

- Correctness.
- Completeness.
- Safety.
- Tone.
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

Agent Self-Evaluation
