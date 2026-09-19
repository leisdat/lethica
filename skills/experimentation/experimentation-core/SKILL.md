# Experimentation Core

## Purpose

A/B test, hipotesis, tracking eksperimen.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Experimentation**.
- Entry point sebelum sub-skill.
- Menentukan alur antar-step domain ini.

## Workflow

Discover
→ Select
→ Delegate
→ Track
→ Verify
→ Report

## Rules

- Hipotesis jelas.
- Metrik.
- Kontrol.
- Significance.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `experimentation-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Experimentation
