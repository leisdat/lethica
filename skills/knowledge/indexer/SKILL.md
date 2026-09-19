# Indexer

## Purpose

Membangun index dari dokumen/source code/notes.

## Kapan Digunakan

- Perlu menjalankan operasi konkret dalam domain **Knowledge / RAG**.
- Setelah validasi pra-syarat terpenuhi.
- Untuk mencapai state akhir yang terverifikasi.

## Workflow

Prepare
→ Execute
→ Capture Output
→ Verify
→ Cleanup

## Rules

- Detect tipe file (md, code, pdf, txt).
- Chunk berdasarkan struktur logis, bukan karakter mentah.
- Simpan metadata: source, path, timestamp, hash.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Failure Handling

- Jika gagal: baca error, identifikasi root cause, perbaiki input/strategi.
- Retry hanya jika aman & terbatas.
- Jika butuh otorisasi: henti & eskalasi, jangan lanjut diam-diam.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Knowledge / RAG
