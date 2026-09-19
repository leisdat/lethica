# Blackboard

## Purpose

Sistem blackboard untuk koordinasi longgar.

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

- Write/read terstruktur.
- Trigger on update.
- Hindari race.
- Cleanup sisa.
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
