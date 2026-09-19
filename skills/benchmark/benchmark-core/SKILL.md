# Benchmark Core

## Purpose

Mengukur kemampuan Lethica.

## Kapan Digunakan

- Mengoordinasikan skill di dalam layer **Benchmark / Evaluation**.
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

- Define → Run → Score → Compare → Report
- Task harus objektif & reproducible.
- Hindari overfit ke set uji.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Berjalan di bawah `benchmark-core`.
- Berkoordinasi dengan `policy` (guardrails) & `state` (checkpoint) bila relevan.
- Hasilnya dapat dikonsumsi `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Benchmark / Evaluation
