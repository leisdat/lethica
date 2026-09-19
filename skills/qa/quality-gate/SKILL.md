# Quality Gate

## Purpose

Menentukan apakah task boleh dianggap selesai.

## Gate

### Code
- implementation complete
- no known critical bug

### Tests
- relevant tests passed
- regression acceptable

### Security
- no known critical security issue

### Build
- build succeeds jika applicable

### Requirements
- acceptance criteria terpenuhi

## Decision

PASS
→ semua requirement dan gate terpenuhi

FAIL
→ ada critical/high blocking issue

PARTIAL
→ sebagian terpenuhi tetapi masih ada limitation

BLOCKED
→ verification tidak dapat dilakukan
