# Resource Core

## Purpose

Mengelola budget CPU/RAM/disk/token/context.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Resource Management**.
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

- Track setiap resource.
- Alert threshold.
- Reclaim idle.
- Prioritas.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `resource-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Resource Management
