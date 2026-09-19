# Architecture Core

## Purpose

Analisis arsitektur, dependency graph, keputusan.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Architecture Intelligence**.
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

- Map komponen.
- Relasi.
- Trade-off.
- Dokumentasi.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `architecture-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Architecture Intelligence
