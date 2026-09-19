# Code Review

## Purpose
Menilai kualitas code sebelum dianggap selesai.

## Review Order

1. Correctness
2. Security
3. Reliability
4. Maintainability
5. Performance
6. Readability

## Check

Cari:

- bug
- race condition
- null/undefined handling
- invalid input
- security issue
- duplicated logic
- unnecessary complexity
- dead code
- breaking change
- poor error handling
- resource leak

## Rules

Prioritaskan bug nyata dibanding style preference.

Jangan meminta perubahan hanya karena berbeda dari personal preference.

## Output

Gunakan:

CRITICAL
HIGH
MEDIUM
LOW
INFO

Untuk setiap finding jelaskan:

- location
- problem
- impact
- recommended fix
