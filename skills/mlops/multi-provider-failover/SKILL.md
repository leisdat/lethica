---
name: multi-provider-failover
description: "Auto-failover antar LLM provider beda rate limit."
---

# Multi-Provider Failover

Routing LLM request lintas provider (routerku, flatkey, xkiro, 9Router) — auto-detect mati/hidup, fallback chain.

## Trigger
- "provider X error/402/403/429"
- "model gak bisa diakses dari routerku"
- "tambah provider baru"
- "routing pintar antar provider"

## Status Provider (2026-09-02)

| Prefix | Provider | Base URL | Frontier? | Keterangan |
|--------|----------|----------|-----------|------------|
| (none) | Routerku Free-All | http://127.0.0.1:20130/v1 | - | deepseek-v4-flash, L=minimax-m3 |
| fk/ | Flatkey | https://router.flatkey.ai/v1 | ✅ Claude Sonnet 5, GPT-5.6 Sol | key: sk-llBuC... (di memory) |
| xk/ | xkiro | https://api.xkiro.com/v1 | ✅ GPT-5.6, Claude Opus 5 | 2 keys stacked |
| kio/ | kiosapi | https://kiosapi.com/v1 | ✅ mimo-v2.5, glm-5.3-flash | |
| bai/ | b.ai | https://api.b.ai/v1 | ✅ banyak | 2 keys |
| tr/ | tokenrouter | https://api.tokenrouter.com/v1 | ✅ | 2 keys |
| or/ | openrouter | https://openrouter.ai/api/v1 | ✅ 421 models | key sk-or-... |
| tabi/ | tabitoken | https://tabitoken.com/v1 | ✅ Claude | sering 429 |

## Error Code → Arti

| Kode | Arti | Action |
|------|------|--------|
| 401 | Key salah/expired | Ganti key, cek provider |
| 402 | Payment required | Skip provider ini, pindah lain |
| 403 | Forbidden (provider down / IP block) | Skip, coba lagi nanti |
| 404 | Model tidak ada | Cek nama model |
| 429 | Rate limit / cooldown | Tunggu, retry dengan backoff |
| 500+ | Provider error | Skip, failover ke next |
| 529 | Upstream overload | Skip, coba lagi nanti |
| 0 | Timeout | Skip, failover |

## Failover Pattern

```python
# Order provider berdasarkan reliability
PROVIDER_CHAIN = [
    ("local",   "http://127.0.0.1:20130/v1", "auto"),
    ("fk",      "https://router.flatkey.ai/v1", "claude-sonnet-5"),
    ("xk",      "https://api.xkiro.com/v1", "claude-opus-5"),
    ("bai",     "https://api.b.ai/v1", "claude-sonnet-5"),
]

for name, base, model in PROVIDER_CHAIN:
    try:
        resp = chat(base, model, messages)
        return resp  # sukses
    except RateLimitError:
        time.sleep(backoff)  # tunggu lalu lanjut
    except ProviderDown:
        continue  # langsung pindah
    except PaymentRequired:
        continue  # skip permanent
```

## Routerku Integration

Routerku (:20130) udah support multi-key rotation & failover antar model dalam combo. Model format: `prefix/model-id`.

**Tambah provider baru ke routerku DB** (`~/.9router/db/data.sqlite`):

```sql
-- 1. Insert node (type openai-compatible)
INSERT INTO providerNodes (id, type, name, data, createdAt, updatedAt)
VALUES ('uuid', 'openai-compatible', 'namaprovider',
  '{"prefix":"px","apiType":"chat","baseUrl":"https://.../v1"}', now, now);

-- 2. Insert connection — PENTING: kolom provider = NODE ID (UUID), bukan prefix!
INSERT INTO providerConnections (id, provider, authType, priority, isActive, data, createdAt, updatedAt)
VALUES ('uuid2', '<NODE_UUID>', 'apikey', 1, 1,
  '{"apiKey":"sk-...","testStatus":"active"}', now, now);
```

**Pitfall kritis**: `providerConnections.provider` harus = `providerNodes.id` (UUID), bukan `prefix`. Kalau salah → provider gak ke-load (loaded N providers tetep sama, prefix gak muncul).

**Auto-reload**: routerku punya watchFile 2s — edit DB langsung ke-reload otomatis. Tapi kadang perlu kill + start ulang kalau ada instance zombie pegang port:

```bash
# kill semua instance routerku
pkill -f "node.*router.mjs"
# cek port free
ss -tlnp | grep 20130
# start ulang (background)
cd ~/routerku && node router.mjs
```

## Health Check

```bash
# Cek provider hidup/mati
for p in "fk:https://router.flatkey.ai/v1:KEY1" ...; do
  name=${p%%:*}; rest=${p#*:}; base=${rest%%:*}; key=${rest#*:}
  code=$(curl -s -o /dev/null -w "%{http_code}" -m 8 "$base/models" -H "Authorization: Bearer $key")
  echo "$name: $code"
done
```

## Pitfalls

- **Instance zombie routerku** — `kill PID` gak selalu matiin semua; ada proses kedua yang pegang port → `EADDRINUSE`. Cek `ps aux | grep router.mjs`, kill SEMUA.
- **403 beda-beda artinya**: bai/tr/or 403 = provider down; xk 403 = IP block. Bedakan dari response body.
- **429 cooldown routerku** — "provider in cooldown" = routerku sendiri yang nge-cool-down provider itu. Tunggu ~1-2 menit, bukan salah key.
- **402 = payment required** — provider butuh top-up. Skip permanent dari chain.
- **Free model (myt/ftf) sering 402** setelah quota habis. Cek testStatus di DB.
- **Tiap provider punya rate limit sendiri**: routerku 60 RPM/5000 RPD per provider (set ROUTERKU_RPM_<PREFIX>).

## Files

- Routerku: `~/routerku/router.mjs` + DB `~/.9router/db/data.sqlite`
- Log: `~/routerku/routerku.log`, `~/.routerku-requests.log`
- Dashboard: `~/routerku/dashboard.html`
