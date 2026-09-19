# Validate

## Purpose

Memvalidasi skill agar tidak rusak.

## Kapan Digunakan

- Perlu memeriksa/mengevaluasi sesuatu dalam domain **Skill Manager**.
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

- Cek SKILL.md ada & bisa dibaca.
- Cek referenced file ada.
- Tolak skill dengan sintaks rusak.
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

Skill Manager
