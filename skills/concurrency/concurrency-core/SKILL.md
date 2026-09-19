# Concurrency Core

## Purpose

Mengelola eksekusi paralel, worker, & queue.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Concurrency / Queue**.
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

- Batas worker.
- Queue backpressure.
- No race.
- Graceful shutdown.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `concurrency-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Concurrency / Queue
