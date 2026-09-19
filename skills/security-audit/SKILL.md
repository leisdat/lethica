# Security Audit

## Purpose
Mendeteksi vulnerability pada aplikasi dan code.

## Check

- hardcoded secrets
- authentication
- authorization
- input validation
- injection
- XSS
- CSRF
- insecure file handling
- path traversal
- unsafe deserialization
- sensitive data exposure
- insecure API
- dependency vulnerability
- logging sensitive information

## Rules

- Jangan menampilkan secret.
- Jangan menyimpan credential ke source code.
- Validasi input dari user.
- Gunakan least privilege.
- Jangan menganggap frontend validation sebagai security boundary.

## Output

Severity:

CRITICAL
HIGH
MEDIUM
LOW

Sertakan:

- vulnerability
- affected location
- impact
- remediation
