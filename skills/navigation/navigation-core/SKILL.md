# Navigation Core

## Purpose

Memahami repo, OS, runtime, & state project.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Navigation / Environment Awareness**.
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

- Map struktur.
- Deteksi runtime.
- Baca env.
- Cache state.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `navigation-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Navigation / Environment Awareness
