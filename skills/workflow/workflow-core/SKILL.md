# Workflow Core

## Purpose

Mengorkestrasi task multi-step otomatis.

## Kapan Digunakan

- Mengoordinasikan skill di dalam layer **Workflow / Automation**.
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

- Define → Compose → Execute → Monitor → Complete
- Setiap step harus memiliki precondition & postcondition.
- Idempoten bila memungkinkan.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Berjalan di bawah `workflow-core`.
- Berkoordinasi dengan `policy` (guardrails) & `state` (checkpoint) bila relevan.
- Hasilnya dapat dikonsumsi `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Workflow / Automation
