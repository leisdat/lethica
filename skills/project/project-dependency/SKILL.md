# Project Dependency

## Purpose

Mengelola hubungan antar task.

## Dependency Types

- blocked-by
- requires
- produces
- conflicts-with

## Rules

Task hanya dijalankan jika dependency wajib sudah selesai.

Task independen boleh dijalankan parallel.

Jika dependency gagal:

→ mark dependent task blocked
→ diagnose
→ recover
→ continue
