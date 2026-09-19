# Search Core

## Purpose

Merencanakan & menjalankan pencarian informasi.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Search Intelligence**.
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

- Query planning sebelum search.
- Multi-source.
- Verify.
- Sintesis.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `search-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Search Intelligence
