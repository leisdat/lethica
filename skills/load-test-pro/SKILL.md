---
name: load-test-pro
description: "Load test websites and APIs with concurrent users."
version: 1.0.0
author: letticha
license: MIT
metadata:
  hermes:
    tags: [testing, performance]
---

# Website Load Tester PRO

Script Python untuk load testing website/API.

## Lokasi File
```
~/load_test_pro.py
```

## Cara Pakai

```bash
python3 ~/load_test_pro.py --url "http://localhost:3001" --users 10 --duration 30
python3 ~/load_test_pro.py --url "http://localhost:3001" --users 20 --duration 30 --output result.json
python3 ~/load_test_pro.py --base "http://localhost:3001" \
  --endpoints '[{"url":"/"},{"url":"/api/users"}]' --users 30 --duration 30
```

## Argumen
| Argumen | Deskripsi | Default |
|---------|-----------|---------|
| `--url` | URL endpoint | Required |
| `--users` | Concurrent users | 10 |
| `--duration` | Durasi (detik) | 30 |
| `--method` | HTTP method | GET |
| `--data` | Request body JSON | None |
| `--output` | Output filename | None |

## Hasil
- Total requests, success/failure rate
- Response time (avg, median, min, max)
- Throughput (req/s)
- Status code distribution
- Error details

## Multi-Endpoint / Pool Limiter Test

Untuk server yang punya **worker pool / concurrency limiter** (mis. NOVA dengan 6 max workers, 3 max downloads), single-URL test gak cukup. Gunakan `~/stress_nova.py`:

```bash
python3 ~/stress_nova.py
```

Script ini:
- **6 endpoint berbeda** (health, state, search, home, security, trending) — sebagian spawn worker
- **50 user konkuren** selama 30 detik
- Mencatat **WORKER_BUSY / WORKER_COOLDOWN** errors buat validasi pool limiter
- 100% Python stdlib + `curl_cffi` kalau terinstall

**Kapan pakai:**
- Habis hardening worker pool → validasi gak overload
- Sebelum deploy → cek backpressure & crash resistance
- Bandingkan throughput sebelum vs sesudah perubahan concurrency

**Performance Record (NOVA — Redmi Note 11, 6GB RAM):**
| Skenario | Users | Throughput | Avg ms | Success |
|----------|-------|-----------|--------|---------|
| Single URL | 5 | 592 req/s | 8ms | 100% |
| Single URL | 10 | 145 req/s | 44ms | 100% |
| Multi-endpoint + pool | 50 | 171 req/s | 281ms | 100% |

Catatan: throughput pool-bound server (NOVA max 6 workers) gak linier dengan jumlah user — request antri di semaphore, bukan crash/error.

## Catatan
- Pure Python stdlib, tidak perlu install package
- Thread-based concurrency
- Progress bar real-time