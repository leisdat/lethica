# Free-vs-Paid Provider Probe Matrix & Combo Repair (verified 2026-09-04)

How to decide whether a provider/key is actually usable for FREE combos, and
the walkthrough of rebuilding `Free-Kombo` from paid junk into 6 verified free
models.

## Verdict matrix — what each error means when probing a candidate provider

| Raw response | Verdict |
|---|---|
| `401 invalid_api_key` / "Invalid token" | Key dead/revoked. Provider unusable until re-credentialed. |
| `402 Payment Required` on `/models` + `insufficient_quota`/"insufficient balance" on chat | Key VALID but pay-as-you-go with zero/low balance. NOT free. |
| `credit insufficient balance: balance=N required=M` | Paid model; M is the per-request cost. M >> N = expensive class (Opus). Never put in a free combo. |
| `No available channel for model X` | Model name wrong or channel delisted upstream. |
| `429 provider in cooldown` | Rate-limited; may recover. Fine in a combo (failover skips it), not fine as sole entry. |
| `Model tidak diizinkan` (myt-style upstreams) | Model removed from the free allowlist. |
| "You've reached today's free limit" (xk-style) | Free tier exists but daily-capped. OK as combo entry, not as sole. |
| 200 + content | Verified working. |

Key distinction the matrix encodes: **401 = auth broken, 402/insufficient_quota =
auth fine, wallet empty.** A valid key with no balance is NOT a free provider.

## Bitdeer (api-inference.bitdeer.ai/v1)

Pay-as-you-go GPU cloud. No free tier. Tested key passed auth but both
`deepseek-ai/DeepSeek-V4-Flash` and `Qwen/Qwen3.8-27B` returned
`insufficient_quota`; `/models` returns bare `402 Payment Required`.
Do not add to free combos.

## Provider state snapshot (VOLATILE — re-probe before relying)

As of 2026-09-04 on user's 9Router DB:
- `bai` (api.b.ai): deepseek-v4-flash, glm-5.3-flash, qwen3.8-flash, minimax-m2.7 — ALL OK
- `tabi` (tabitoken): claude-opus-5 = PAID (91k credits/req), claude-opus-5-thinking = model_not_found. Connection `testStatus=unavailable, errorCode=429`.
- `asc` / `ascopus`: token dead (401 Invalid token) — needs re-credential
- `xk`: qwen3.8-max:free hit daily free limit that day
- `myt`: mimo-v2.5-free delisted; gemini-3.5-flash-free in 429 cooldown
- `or`: minimax/minimax-m3:free OK; `tr`: z-ai/glm-5.3-free OK

## Free-Kombo repair walkthrough (worked end-to-end)

1. `sqlite3` CLI absent → read combos via Python stdlib:
   ```python
   import sqlite3, json
   c = sqlite3.connect(os.path.expanduser("~/.9router/db/data.sqlite")).cursor()
   c.execute("SELECT models FROM combos WHERE name='Free-Kombo'")
   ```
2. Old contents: `bai/minimax-m2.7`, `tabi/claude-opus-5-thinking`,
   `tabi/claude-opus-5` — 2 of 3 paid/dead, hence the billing error.
3. DB triage: parse `providerConnections.data` JSON → `testStatus`, `errorCode`,
   `backoffLevel` per prefix (tabi = unavailable/429).
4. Live-probe candidates through routerku (:20130) with `max_tokens:5`; keep
   only 200-OK answers → 6 survivors (bai×4, or minimax-m3:free, tr glm-5.3-free).
5. `UPDATE combos SET models=? WHERE name='Free-Kombo'` — no router restart;
   watchFile reloaded in ~4s.
6. Verify by requesting the combo NAME: response `model` field showed
   `minimax/minimax-m3:free` (bai was in cooldown from step-4 probing) —
   failover demonstrably working. Content echoed the canary string.

## Router key for local probes

Active inbound key: `SELECT key FROM apiKeys WHERE isActive=1` (full strings in
the DB). Bearer it against `http://127.0.0.1:20130/v1/chat/completions`.
