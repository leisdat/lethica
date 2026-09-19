# Rollback

## Trigger

Rollback jika:

- critical functionality broken
- severe regression
- security issue
- service unavailable
- migration failure

## Workflow

Detect
→ Confirm
→ Rollback
→ Health Check
→ Monitor
→ Investigate

## Rules

Rollback harus mengembalikan service ke known-good state.

Jangan melakukan rollback database secara sembarangan.
