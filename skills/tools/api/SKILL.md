# API

## Purpose
Interaksi HTTP / API eksternal dan internal.

## Rules

- Validasi request sebelum kirim.
- Tangani HTTP status (2xx, 4xx, 5xx).
- Tangani timeout.
- Tangani response malformed.
- Jangan log secret (token / key / password).
- Gunakan header yang tepat (Content-Type, Authorization).
- Hormati rate limit.

## Workflow

define endpoint + method
→ build request (headers, body)
→ send
→ inspect status + body
→ parse
→ verify

## Auth

- Bearer token
- API key (header / param)
- OAuth (jika didukung)
- Jangan hardcode credential — gunakan env / secret manager.

## Avoid

- mengirim secret ke log
- ignore error status
- retry tanpa backoff
- trust response tanpa validasi schema
