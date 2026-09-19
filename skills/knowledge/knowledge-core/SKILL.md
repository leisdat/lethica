# Knowledge Core

## Purpose

Mengelola knowledge base Lethica: indexing, retrieval, sinkronisasi.

## Kapan Digunakan

- Mengoordinasikan skill di dalam layer **Knowledge / RAG**.
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

- Index → Store → Retrieve → Re-rank → Answer
- Gunakan sumber yang sudah diverifikasi.
- Jangan mengklaim knowledge sebagai fakta tanpa retrieval.
- Versioning knowledge saat sumber berubah.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Berjalan di bawah `knowledge-core`.
- Berkoordinasi dengan `policy` (guardrails) & `state` (checkpoint) bila relevan.
- Hasilnya dapat dikonsumsi `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Knowledge / RAG
