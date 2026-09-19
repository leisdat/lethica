# Task Delegation

## Purpose

Mendelegasikan sub-tugas ke agent lain.

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

- Pilih agent by capability.
- Sertakan konteks cukup.
- Track status.
- Reassign bila gagal.
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
