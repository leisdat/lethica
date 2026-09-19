# Provider Catalog Quirks

Notes harvested from Free Claude Code (FCC) catalog audit + 9Router live
probes, September 2026. Use this when deciding which provider prefix to
trust for a given task.

## Front-end panels (model name lies)

These providers all run on top of the Chinese "new-api" panel (clone of
one-api). The DB model id you see doesn't match what the upstream
actually serves. The router has no way to know — `model: "X"` in the
response is whatever the front-end wants to label it.

| Provider | Prefix | Real upstream | Remap example |
|---|---|---|---|
| `api.hcnsec.cn` | `hc` | shared new-api pool | `hc/glm-5.3-flash` → `meituan/LongCat-2.0:free` |
| `kiosapi.com` | `kio` | new-api | model name is whatever the operator set |
| `router.kiosapi.com` | `rk` | new-api (different account!) | has actual quota if account funded |
| `linstore.my.id` | (no prefix in router) | new-api mirror | quota $0 — mirror of `modelrouter.web.id` |
| `modelrouter.web.id` | `mr` | new-api | 93 models, all quota $0 |

**Lesson**: do not rely on `response.model` to verify the actual model.
Test by capability (`response.embedding[0].length` for dimension, code
output shape for code models, etc.) not by name.

## Working free providers (verified Sept 2026)

| Prefix | Provider | Models live | Note |
|---|---|---|---|
| `gr` | gorouter.app | 2 (`claude-opus-5`, `claude-opus-5-thinking`) | gold — gets you Opus 5 free |
| `rk` | router.kiosapi.com | 23 (glm-5.2, qwen3-8b, agnes, claude-opus-5, etc.) | best of new-api lot |
| `hc` | api.hcnsec.cn | 19 | includes `Qwen3-Embedding-8B` (2048d) |
| `bai` | api.b.ai | 47 | solid, paid-tier bills eventually |
| `or` | openrouter.ai | 427 | free route: `minimax/minimax-m3:free`; rest pay-as-go |
| `tr` | tokenrouter.com | 134 | free route: `z-ai/glm-5.3-free` |
| `gg` | generativelanguage.googleapis.com | 55 | Gemini via Google's own OpenAI-compat, has free tier |
| `zl` | zanslab.id | 24 | small but reliable |

## Dead (don't bother)

| Prefix | Why |
|---|---|
| `xg` | xAI API, paid only |
| `cag`×3 | cutad.web.id — quota exhausted 2025 |
| `moonshot` | token revoked, cooldown L10 |
| `ftf` | freetokenfaucet.com — SSL cert invalid |
| `tabi` | tabitoken.com — paid only |
| `zg` | api.z.ai (GLM) — key cooldown L9, never recovers |
| `xk` (one of two) | unknown provider, returns 403 |
| `muse-spark-1.2-contributor` | reasoning-only, content field is null |

## Quota gotchas

- `minimax/minimax-m3:free` via OpenRouter: works, but slows down when
  you hammer it. The router cascades to it first → it becomes the
  single point of failure for the whole `Free-Kombo` combo.
- `hc/` has 50 000 token daily allocation per key; one probe eats ~200
  tokens. Don't `discoverModels` more than 2×/day.
- `gorouter.app` claude-opus-5: appears unlimited in practice but the
  upstream is rate-limited per IP. If you go over, expect 429 for ~1h.
- `modelrouter.web.id` quota reads `$0.000000` even when "active" — the
  panel has fake billing display. Don't trust the dashboard.

## Key redemption quirks

- Kiro (AWS Builder ID): 1 account = 1 API key, no bulk farming
- antigravity CLI OAuth: internal ID ≠ alias; some versions 3.7 OK,
  3.8 403
- Grok CLI: free tier throttles aggressively after 1k tokens/day
- GitHub Models: free if you have a GitHub PAT, model list rotates
  monthly

## Reference

- See `references/9router-db-schema.md` for the full SQLite layout.
- See `termux-dev/references/scraper-audit-repair.md` for general
  probe-per-capability audit pattern (used here to verify these
  providers).
