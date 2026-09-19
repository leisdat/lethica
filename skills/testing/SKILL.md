# Testing

## Purpose
Memastikan perubahan bekerja dan tidak merusak functionality existing.

## Test Levels

Gunakan sesuai kebutuhan:

- unit test
- integration test
- API test
- UI test
- end-to-end test
- regression test

## Test Cases

Minimal pertimbangkan:

- expected input
- empty input
- invalid input
- boundary value
- failure case
- permission/access case
- existing functionality

## Rules

- Test behavior, bukan implementation detail yang tidak penting.
- Jangan menghapus test hanya karena gagal.
- Jangan membuat test palsu yang selalu pass.
- Jangan skip failure tanpa alasan.

## Completion

Perubahan dianggap verified jika test relevan berhasil atau limitation dijelaskan.
