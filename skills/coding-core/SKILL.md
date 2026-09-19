# Coding Core

## Purpose
Menjadi sistem utama Lethica untuk mengembangkan, memperbaiki, dan memodifikasi software secara aman dan terstruktur.

## Core Workflow

Selalu gunakan:

1. Understand
2. Inspect
3. Plan
4. Implement
5. Run
6. Test
7. Debug
8. Review
9. Verify

Jangan langsung coding sebelum memahami project.

## 1. Understand

Identifikasi:

- tujuan user
- fitur yang diminta
- behavior yang diharapkan
- batasan
- platform
- framework
- bahasa pemrograman
- kondisi existing project

Jika requirement ambigu, gunakan konteks project dan instruksi terbaru.

## 2. Inspect

Sebelum mengubah code:

- baca struktur project
- cari file terkait
- baca implementation yang sudah ada
- cari reusable component/function
- cek konfigurasi
- cek dependency
- cek entry point
- cek test yang tersedia

Jangan membuat file baru jika functionality sudah tersedia.

## 3. Plan

Buat rencana minimal:

- file yang akan diubah
- file yang perlu dibuat
- logic yang perlu ditambahkan
- dependency yang diperlukan
- risiko perubahan
- cara testing

Hindari overengineering.

## 4. Implement

Rules:

- gunakan pattern existing project
- gunakan naming convention existing
- gunakan dependency yang sudah tersedia
- jangan mengubah API tanpa alasan
- jangan merusak backward compatibility
- jangan menghapus functionality yang tidak diminta
- jangan membuat duplicate implementation
- gunakan error handling yang sesuai

Implement perubahan sekecil mungkin untuk mencapai tujuan.

## 5. Run

Setelah implementasi:

- jalankan aplikasi/build jika memungkinkan
- jalankan formatter
- jalankan linter
- cek runtime error

Jangan menganggap code benar hanya karena syntax valid.

## 6. Test

Test:

- normal case
- edge case
- invalid input
- error handling
- integration dengan code existing

Jika test belum tersedia dan perubahan cukup besar, buat test yang relevan.

## 7. Debug

Jika terjadi error:

1. baca error lengkap
2. identifikasi lokasi
3. reproduksi
4. cari root cause
5. perbaiki root cause
6. jalankan ulang test

Jangan hanya menutupi error dengan try/catch.

## 8. Review

Periksa:

- correctness
- readability
- maintainability
- security
- performance
- duplicate code
- unnecessary dependency
- regression

## 9. Verify

Sebelum menyatakan selesai, pastikan:

- requirement terpenuhi
- code berjalan
- test berhasil
- tidak ada regression yang diketahui
- perubahan sesuai scope

## Scope Discipline

Jangan:

- redesign project tanpa diminta
- rewrite framework
- upgrade dependency besar tanpa alasan
- menghapus code lama secara sembarangan
- membuat abstraksi berlebihan
- memperbaiki hal yang tidak berhubungan

## Completion Report

Setelah selesai laporkan:

- What changed
- Files changed
- Tests run
- Result
- Remaining issues
