# Sandbox Core

## Purpose

Menjalankan kode/command di lingkungan terisolasi.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Simulation / Sandbox**.
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

- Isolate FS/network.
- Resource limit.
- Ephemeral.
- Cleanup.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `sandbox-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Simulation / Sandbox
