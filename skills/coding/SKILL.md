# Coding Skill

Aktifkan agent untuk membangun, memodifikasi, debug, test, dan menyempurnakan software secara andal.
Agent harus berperilaku seperti developer berpengalaman, bukan sekadar generator kode.

## Core Workflow

```
Understand
  ↓
Inspect
  ↓
Plan
  ↓
Implement
  ↓
Run
  ↓
Test
  ↓
Debug
  ↓
Review
  ↓
Verify
```

JANGAN lewati inspection saat bekerja dengan project yang sudah ada.

## 1. Understand

Sebelum coding, tentukan:

- Goal aktual user
- Expected behavior
- Fungsionalitas yang sudah ada
- Constraints
- Technology stack
- File yang relevan

JANGAN implementasi berdasar asumsi bila project sudah berisi informasi yang dibutuhkan.

## 2. Inspect

Untuk project yang sudah ada:

- Inspect struktur project.
- Baca file relevan.
- Identifikasi entry points.
- Identifikasi dependencies.
- Cek pola yang sudah ada.
- Pahami bagaimana komponen berinteraksi.

JANGAN rewrite project secara tidak perlu.

## 3. Plan

Untuk task non-trivial:

```
Goal
├── Files to modify
├── Components/functions involved
├── Dependencies
├── Implementation steps
└── Verification
```

Jaga rencana proporsional dengan task. Perubahan sederhana tidak butuh planning berlebihan.

## 4. Implement

Saat menulis kode:

- Ikuti konvensi project yang ada.
- Prefer solusi sederhana.
- Reuse komponen & utilitas existing.
- Hindari dependency tidak perlu.
- Jaga fungsi/komponen tetap fokus.
- Tangani error dengan wajar.
- Validasi input eksternal.
- Hindari hardcoded secrets.
- Pertahankan behavior existing kecuali user minta perubahan.

## 5. Existing Code First

Sebelum membuat yang baru, cek apakah project sudah punya:

- Sebuah komponen
- Sebuah utility
- Sebuah helper
- Sebuah service
- Sebuah konfigurasi
- Sebuah design system
- Sebuah API wrapper

Reuse infrastruktur existing bila sesuai.

## 6. Run

Setelah implementasi:

- Jalankan aplikasi atau command relevan.
- Cek build output.
- Cek console/log errors.
- Verifikasi fungsionalitas yang diubah.

JANGAN asumsikan kode jalan hanya karena terlihat benar.

## 7. Test

Test:

- Normal behavior
- Edge cases
- Invalid input
- Error states
- Fungsionalitas existing yang relevan

Gunakan framework testing project yang ada bila tersedia.

## 8. Debug

Saat error muncul:

```
Error
  ↓
Reproduce
  ↓
Inspect stack trace
  ↓
Find root cause
  ↓
Fix
  ↓
Run again
```

JANGAN ubah sembarangan kode yang tidak terkait.

## 9. Review

Sebelum selesai, cek:

**Correctness** — Apakah benar-benar menyelesaikan masalah yang diminta?

**Security** — Apakah implementasi memperkenalkan vulnerabilitas?

**Performance** — Apakah ada pekerjaan mahal yang tidak perlu?

**Maintainability** — Apakah developer lain akan paham kodenya?

**Consistency** — Apakah mengikuti arsitektur project yang ada?

**UX** — Jika user-facing, apakah interaksi berperilaku benar?

## 10. Refactoring

Refactor hanya bila berguna.

Alasan bagus:

- Menghapus duplikasi
- Menyederhanakan kode kompleks
- Meningkatkan maintainability
- Memperbaiki masalah arsitektur
- Meningkatkan performa

JANGAN rewrite kode yang sudah working hanya agar terlihat beda.

## 11. Dependencies

Sebelum menambah dependency:

- Cek apakah dependency existing bisa menyelesaikan masalah.
- Pertimbangkan bundle size.
- Pertimbangkan security.
- Pertimbangkan maintenance.
- Pertimbangkan compatibility.

Hindari menambah dependency untuk fungsionalitas trivial.

## 12. Frontend

Untuk kerja frontend:

- Buat layout responsive.
- Gunakan komponen reusable.
- Tangani loading states.
- Tangani error states.
- Tangani empty states.
- Sediakan keyboard/focus states.
- Hindari animasi tidak perlu.
- Ikuti design system project.
- Test perilaku mobile dan desktop.

Jika skill `design-reference` atau `anti-ai-slop` ada, gunakan itu.

## 13. Backend

Untuk kerja backend:

- Validasi input.
- Tangani error.
- Autentikasi operasi terproteksi.
- Otorisasi akses.
- Hindari membocorkan secrets.
- Gunakan logging yang tepat.
- Tangani kegagalan database.
- Pertimbangkan rate limiting bila sesuai.

## 14. API

Saat bekerja dengan API:

- Validasi requests.
- Tangani HTTP errors.
- Tangani timeouts.
- Tangani respon malformed.
- Hindari kebocoran informasi sensitif.
- Pisahkan logika API dari UI bila sesuai.

## 15. Database

Saat memodifikasi perilaku database:

- Pahami schema existing.
- Pertahankan data integrity.
- Pertimbangkan migrations.
- Validasi data.
- Tangani query gagal.
- Hindari operasi destruktif kecuali explicit diminta.

## 16. Security

JANGAN pernah:

- Hardcode passwords.
- Hardcode API keys.
- Commit secrets.
- Disable security checks hanya agar kode jalan.
- Eksekusi input tak terpercaya begitu saja.
- Bypass authentication atau authorization.

Gunakan environment variables atau sistem secret-management project yang ada.

## 17. Completion Criteria

JANGAN nyatakan task coding selesai sampai:

- Fungsionalitas yang diminta terimplementasi.
- Kode relevan jalan.
- Test relevan lulus bila tersedia.
- Error penting teratasi.
- Tidak ada regresi obvious yang diperkenalkan.
- Implementasi final cocok dengan requirement user.

Jika sesuatu tidak bisa diverifikasi, nyatakan secara jelas.

## Final Principle

Tulis kode lebih sedikit, tapi buat kode benar, maintainable, testable, dan sesuai untuk project.
