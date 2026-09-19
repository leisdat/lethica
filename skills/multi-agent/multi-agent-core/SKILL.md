# Multi Agent Core

## Purpose

Mengatur kolaborasi antar-agent: pesan, context bersama, resolusi konflik.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Multi-Agent Collaboration**.
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

- Define protokol pesan antar-agent.
- Gunakan context bersama yang ter-versi.
- Resolusi konflik via voting/arbiter jelas.
- Hindari loop agent-to-agent tanpa terminasi.
- Log setiap handoff.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `multi-agent-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Multi-Agent Collaboration
