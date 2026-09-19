# Self Healing Core

## Purpose

Detect failure→diagnose→repair→verify.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Self-Healing**.
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

- Monitor.
- Isolate cause.
- Auto-fix aman.
- Verify.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `self-healing-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Self-Healing
