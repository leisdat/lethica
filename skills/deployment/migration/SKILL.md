# Database Migration

## Workflow

Inspect
→ Backup Strategy
→ Apply Migration
→ Verify
→ Monitor

## Rules

- Jangan menjalankan migration destructive tanpa verification.
- Pertimbangkan backward compatibility.
- Migration production harus reversible jika memungkinkan.
- Jangan menghapus data hanya untuk memperbaiki schema.
