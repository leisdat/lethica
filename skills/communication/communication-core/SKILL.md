# Communication Core

## Purpose

Mengelola komunikasi keluar & masuk.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Communication**.
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

- Format sesuai channel.
- Respect rate-limit.
- No secret leak.
- Verify delivery.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `communication-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Communication
