# Debugging

## Purpose
Menemukan dan memperbaiki root cause error.

## Workflow

1. Capture error
2. Reproduce
3. Locate
4. Analyze
5. Identify root cause
6. Fix
7. Test
8. Verify

## Rules

- Jangan menebak root cause tanpa evidence.
- Baca traceback/log lengkap.
- Bedakan symptom dan root cause.
- Jangan menambahkan workaround sebelum memahami masalah.
- Jangan menghapus error message hanya agar terlihat berhasil.
- Setelah fix, reproduksi kembali kasus yang gagal.

## Failure Classification

Classify error sebagai:

- syntax
- runtime
- logic
- dependency
- configuration
- environment
- network
- database
- permission
- concurrency
- performance
- security

## Retry

Jangan melakukan retry tanpa batas.

Jika solusi pertama gagal:

1. analisis hasil
2. ubah pendekatan
3. coba kembali
4. jika tetap gagal, laporkan blocker
