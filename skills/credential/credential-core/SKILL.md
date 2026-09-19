# Credential Core

## Purpose

Mengelola API key, token, & secret vault secara aman.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Credential / Secret Management**.
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

- Jangan hardcode di source.
- Encrypt at rest.
- Rotate berkala.
- Audit akses.
- Least privilege.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `credential-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Credential / Secret Management
