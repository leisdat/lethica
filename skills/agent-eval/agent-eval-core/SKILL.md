# Agent Eval Core

## Purpose

Menilai kualitas output sebelum ke user.

## Kapan Digunakan

- Mengoordinasikan skill dalam layer **Agent Self-Evaluation**.
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

- Criteria jelas.
- Self-check.
- Gate.
- Feedback.
- Jangan asumsikan sukses tanpa verifikasi.
- Catat keputusan & hasil agar dapat diaudit.

## Integration

- Di bawah `agent-eval-core`.
- Koordinasi `policy` & `state` bila relevan.
- Konsumable `analytics` & `learning`.

## Cross-Layer

- Guardrails: `policy/*`
- State: `state/*`
- Learning: `learning/*`
- Analytics: `analytics/*`

## Layer

Agent Self-Evaluation
