# Network Core

## Purpose

Interaksi jaringan & web aman.

## Kapan Digunakan

- Mengoordinasikan skill di dalam layer **Network / Web**.
- Sebagai entry point sebelum sub-skill dijalankan.
- Saat perlu menentukan alur antar-step dalam domain ini.

## Workflow

Discover
→ Select
→ Delegate
→ Track
→ Verify
→ Report

## Rules

- Plan → Request → Inspect → Handle → Verify
- Respect robots & rate-limit.
- Jangan abuse target.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Berjalan di bawah `network-core`.
- Berkoordinasi dengan `policy` (guardrails) & `state` (checkpoint) bila relevan.
- Hasilnya dapat dikonsumsi `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Network / Web
