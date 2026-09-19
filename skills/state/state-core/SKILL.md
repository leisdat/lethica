# State Core

## Purpose

Mengelola state & cache antar sesi.

## Kapan Digunakan

- Mengoordinasikan skill di dalam layer **State / Cache**.
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

- Capture → Persist → Restore → Invalidate
- Pisahkan ephemeral vs persistent.
- Jangan simpan secret di state.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Berjalan di bawah `state-core`.
- Berkoordinasi dengan `policy` (guardrails) & `state` (checkpoint) bila relevan.
- Hasilnya dapat dikonsumsi `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

State / Cache
