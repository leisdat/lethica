# Message Bus

## Purpose

Transport pesan antar-agent.

## Kapan Digunakan

- Tugas masuk ke spesialisasi **Multi-Agent Collaboration**.
- Butuh eksekutor konteks sempit.
- Agent umum kurang presisi.

## Workflow

Receive Task
→ Load Context
→ Execute
→ Self-Check
→ Handoff

## Rules

- Async & reliable.
- Idempoten terhadap duplicate.
- Route by topic/agent-id.
- Timeout & dead-letter.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Boundaries

- Kerja hanya di domain.
- Delegasikan bila diluar.
- Laporkan ketidakpastian.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Multi-Agent Collaboration
