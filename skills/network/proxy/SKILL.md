# Proxy

## Purpose

Routing lalu lintas.

## Kapan Digunakan

- Perlu menjalankan operasi konkret dalam domain **Network / Web**.
- Setelah validasi pra-syarat terpenuhi.
- Untuk mencapai state akhir yang terverifikasi.

## Workflow

Prepare
→ Execute
→ Capture Output
→ Verify
→ Cleanup

## Rules

- Tor/socks/http proxy.
- Rotasi identitas.
- Enforce OPSEC.
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

Network / Web
