# Integration Core

## Purpose

Mengelola koneksi Lethica dengan external service.

## Workflow

Discover
→ Authenticate
→ Connect
→ Validate
→ Execute
→ Handle Error
→ Verify

## Rules

- Jangan hardcode credentials.
- Setiap integration harus memiliki error handling.
- External service dianggap untrusted.
- Validate response.
- Gunakan timeout.
- Jangan retry tanpa batas.
