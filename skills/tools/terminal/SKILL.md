# Terminal

## Purpose
Menjalankan command-line operation.

## Rules

Sebelum command:

- pahami tujuan
- cek working directory
- cek command
- pertimbangkan efek samping

Untuk command destructive:

- pastikan target
- pastikan scope
- jangan wildcard sembarangan

## Safe Workflow

pwd
→ inspect
→ execute
→ inspect output
→ verify

## Avoid

- command tidak relevan
- infinite loop
- destructive command tanpa alasan
- menjalankan script asing tanpa memahami tujuan
- membocorkan secret dalam command/output

## Output

Catat:

- command
- result
- exit code
- error
