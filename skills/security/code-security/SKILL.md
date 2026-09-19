# Code Security

## Check

- injection
- XSS
- CSRF
- path traversal
- unsafe deserialization
- command execution
- SSRF
- insecure file upload
- race conditions
- memory/resource abuse

## Rules

Treat all external input as untrusted.

Validate
→ Sanitize
→ Authorize
→ Execute
