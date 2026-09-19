# Skill Manager Core

## Purpose

Mengelola siklus hidup skill Lethica.

## Kapan Digunakan

- Mengoordinasikan skill di dalam layer **Skill Manager**.
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

- Discover → Validate → Load → Track → Update
- Setiap skill wajib punya SKILL.md.
- Catat versi & dependencies.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Berjalan di bawah `skill-manager-core`.
- Berkoordinasi dengan `policy` (guardrails) & `state` (checkpoint) bila relevan.
- Hasilnya dapat dikonsumsi `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Skill Manager
