# Plugin Core

## Purpose

Ekosistem plugin: discovery, kompatibilitas, lifecycle.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Plugin Ecosystem**.
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

- Isolasi plugin.
- Versioned.
- Sandbox.
- Permission jelas.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `plugin-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Plugin Ecosystem
