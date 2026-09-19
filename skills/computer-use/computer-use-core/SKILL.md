# Computer Use Core

## Purpose

Berinteraksi dengan GUI via mouse/keyboard/screenshot.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Computer Use**.
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

- Capture → Reason → Act → Verify.
- Jangan aksi destruktif tanpa konfirmasi.
- Idempoten.
- Timeout per langkah.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `computer-use-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Computer Use
