# Deployment

## Purpose
Menyiapkan dan meluncurkan aplikasi ke environment target dengan aman.

## Workflow

1. Build
2. Verify build output
3. Prepare environment
4. Configure secrets
5. Deploy
6. Smoke test
7. Monitor
8. Rollback plan

## Rules

- Jangan commit secret ke repository.
- Gunakan environment variables atau secret manager.
- Backup state sebelum deploy destruktif.
- Verify di staging bila memungkinkan sebelum production.
- Catat versi / commit yang dideploy.

## Verification

Setelah deploy cek:

- Aplikasi respond
- Endpoint utama jalan
- Tidak ada error fatal di log
- Database connection OK
- Static assets ter-serve

## Rollback

Siapkan cara kembali ke versi sebelumnya:

- Tag / commit reference
- Backup database bila perlu
- Langkah revert yang jelas

Jangan biarkan deploy gagal tanpa rencana recovery.
