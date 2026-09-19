# Secret Scanner

## Detect

Cari kemungkinan:

- API keys
- passwords
- tokens
- private keys
- database credentials
- cloud credentials
- session secrets

## Rules

Jika secret ditemukan:

1. Jangan tampilkan nilainya.
2. Tandai lokasi.
3. Sarankan environment variable/secret manager.
4. Jika sudah ter-commit, anggap compromised.
5. Sarankan rotation.

Jangan mencetak secret ke log.
