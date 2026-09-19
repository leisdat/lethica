# Termux/Android runtime facts (v0.5)

Verified on Redmi Note 11, Helio G96, 6GB RAM, Android 13, no root, Termux-only. Last updated: 2026-09-04.

## LLM provider: routerku

- Default gateway: `http://127.0.0.1:20130/v1`
- Health: `curl -s http://127.0.0.1:20130/v1/health | python -m json.tool`
- API key: `HERMES_CUSTOM_127_0_0_1_20130_API_KEY` in `~/.hermes/.env`
- Combos: `L`, `Free-Kombo`, `Free-All`, `L1`, `L3`
- Free-Kombo is the default for the agent — fills the prompt with 17 free models and round-robins.
- Free-All: every free provider, slower but higher availability.
- Cooldown: 429 → 20s; billing → 120s.
- `reasoning_content` is passed through from upstream (don't strip it; it's a feature for GLM/DeepSeek).

## Model aliases (v0.5)

- `default` → `deepseek-v4-flash` (free, fast, refuses most red-team)
- `code` → `qwen-coder-32b` via `fk/qwen-coder-32b` (strongest free coder)
- `reasoning` → `glm-5.3` via `fk/glm-5.3` (less refusal, larger context)
- `cheap` → `Free-Kombo` (default for agent)
- `quality` → `Free-All` (slower, last-resort)

## Free-tier model matrix (sampled 2026-09-04)

| Model | Free | Refusal | Speed | Notes |
|-------|------|---------|-------|-------|
| `deepseek-v4-flash` | ✓ | strict | fast | default; refuses 5/6 red-team |
| `qwen-coder-32b` | ✓ | medium | medium | best for code; refuses obvious "keygen" |
| `glm-5.3` | ✓ | loose | medium | passes most red-team; longer ctx |
| `minimax-m3` | ✓ | medium | medium | 5/6 refuses; creative writing |
| `kiro` | ✓ (deprecated) | medium | medium | RISK_NOTICE in 9Router; avoid |
| `antigravity-3.7` | ✓ | strict | fast | free tier 3.7 OK, 3.8 403 |

## Path conventions

- Home: `/data/data/com.termux/files/home`
- Agent root: `~/agent/`
- Agent sandbox: `~/agent/sandbox/` (artifact workdir)
- Agent state: `~/agent/state/<task_id>.json` (checkpoint)
- Agent logs: `~/agent/logs/<task_id>.log` (per-step trace)
- Hermes env: `~/.hermes/.env` (READ-ONLY for the agent; access denied on direct read)
- 9Router DB: `~/.hermes/9router/.../db.sqlite` (provider config)
- Skills: `~/.hermes/skills/`

## Filesystem quirks

- No `/tmp` semantics that survive reboot — use `~/agent/sandbox/` for any state you want to keep.
- `/data/data/com.termux/files/usr/bin/` is where `pkg install` lands; check this if a binary "isn't found".
- `pkg` not `apt`. `apt` is an alias to `apt-get` on Termux but `pkg install` is the canonical command.
- Termux has no `/proc/version` consistent with desktop Linux; `uname -a` returns "Linux localhost ...".
- No systemd. Use `pm2` for long-running daemons.

## Process management

- PM2 is the canonical supervisor. `pm2 start "python -m agent ..."` then `pm2 list` / `pm2 logs`.
- Kill background tasks: `pm2 stop <name>`, `pm2 delete <name>`.
- Monitor context switches if the agent runs long: `cat /proc/<pid>/status | grep ctxt`. If `voluntary_ctxt_switches` > 1M, the process is leaking — restart it.
- 9Router (port 20130) and the agent (varies) are both PM2-managed in this setup.

## Common failure modes on Termux

- `pkg not found` → Termux packages may have moved; try `pkg update && pkg upgrade` first.
- Python `ModuleNotFoundError` for stdlib modules → install via `pip install` (NOT system Python, use `python -m pip`).
- 6 GB RAM is enough for 1-3B Q4 local LLMs; 7B is tight and will swap.
- Battery saver kills background processes; pin Termux to "no battery optimization" in Android settings.

## Useful one-liners

```bash
# Health
bash ~/.hermes/heartbeat.sh

# Agent quick test
cd ~/agent && python -m agent "jawab 1 kata: planet terdekat matahari" --budget-iters 4

# Restart everything
pm2 restart all

# Inspect agent task
ls -lt ~/agent/state/ | head -5
cat ~/agent/logs/<latest>.log | tail -50
```

## See also

- `llm-router-failover` — provider routing + cooldown logic
- `9router` — provider SQLite management
- `multi-provider-failover` — combo + auto-reload
- `llm-router-failover` — DB hot-reload on provider change
