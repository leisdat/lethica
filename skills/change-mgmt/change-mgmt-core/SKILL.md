# Change Mgmt Core

## Purpose

Mengelola diff, approval, rollback, history.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Change Management**.
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

- Diff jelas.
- Approval sensitif.
- Rollback siap.
- Audit.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `change-mgmt-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Change Management
