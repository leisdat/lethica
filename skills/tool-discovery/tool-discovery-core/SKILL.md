# Tool Discovery Core

## Purpose

Agent mencari tool paling cocok otomatis.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Tool Discovery**.
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

- Index tool tersedia.
- Match intent.
- Score.
- Cache.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `tool-discovery-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Tool Discovery
