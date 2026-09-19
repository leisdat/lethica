# Process Manager

## Purpose
Mengelola service, daemon, dan proses berjalan.

## Rules

- Ketahui apa yang dijalankan sebelum start / kill.
- Gunakan background mode untuk server / watcher.
- Catat PID / session untuk manajemen.
- Jangan kill proses sistem penting.
- Verifikasi proses hidup setelah start.

## Workflow

identify process
→ start (foreground / background)
→ verify (health check / ps)
→ monitor log
→ stop / restart bila perlu

## Common

- start: jalankan service
- stop: hentikan bersih
- restart: terapkan perubahan
- poll / wait: tunggu kondisi

## Avoid

- kill -9 sembarangan
- background tanpa mekanisme monitor
- menjalankan banyak instance tanpa koordinasi
- lupa bersihkan proses orphan
