---
name: agent-loop
description: Build/run a goal-driven Python agent with skill plugins.
version: 0.7.0
---

# Goal-driven Python agent (the ~/agent pattern)

A small, modular autonomous agent that takes a **goal** in natural language, **plans** steps, **executes** them via pluggable skills/tools, **evaluates** whether the goal is met, and **loops** until done or budget exhausted. Designed for Termux/Android but the architecture is portable.

## When to use this skill

- "Build me an agent that can X autonomously"
- "Add a new skill to the agent"
- "The agent loop is stuck in retry / finished too early / never finished"
- "Make the agent resume after a crash"
- "The agent's LLM evaluator says done but the goal isn't really done"
- "Skill plugin import fails with `attempted relative import` / `'agent' is not a package`"

## Architecture (the loop in one diagram)

```
                ┌─────────────────────────────────────┐
                │            AGENT LOOP               │
                │                                     │
   User goal ──►│  Planner (LLM)                       │
                │     │  produces step queue           │
                │     ▼                                │
                │  Executor (dispatch)                 │
                │     │  calls tool / skill / file     │
                │     ▼                                │
                │  Evaluator (LLM + rules)             │
                │     │  done? retry? continue? replan?│
                │     ▼                                │
                │  Budget guard (tokens/iter/timeout)  │
                │     │                                │
                │     └──► loop back to Planner        │
                └─────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
         Provider         Skill          State
         Router           Registry       (JSON
         (routerku:20130) (auto-load)    checkpoint)
```

## Reference implementation layout

```
~/agent/
├── __init__.py            # makes `agent` a package
├── __main__.py            # CLI entry — `python -m agent "goal"`
├── core/
│   ├── loop.py            # the main loop
│   ├── planner.py         # LLM-based plan / re-plan
│   ├── executor.py        # dispatch step → tool / skill / file
│   ├── evaluator.py       # LLM-based eval + rule fallback
│   ├── memory.py          # state JSON + checkpoint / resume
│   ├── budget.py          # token/iter/timeout accounting
│   ├── router.py          # LLM provider client (routerku)
│   ├── registry.py        # skill auto-loader
│   ├── reporter.py        # stdout + log + Telegram
│   ├── sandbox.py         # permission layer
│   ├── policy.py          # read/write/exec whitelist + deny
│   └── prompts.py         # PLANNER_SYS, EVALUATOR_SYS
├── skills/
│   ├── builtin/           # shipped skills
│   │   ├── code.py        # generate/refactor/debug/explain code
│   │   ├── scraping.py    # fetch URL + extract text
│   │   └── web_research.py# multi-URL + summarize
│   └── user/              # user-defined skills (same contract)
├── state/                 # task JSON checkpoints (one file per task)
├── logs/                  # per-task logs
├── sandbox/               # scratch workdir for file artifacts
└── README.md
```

## Run

```bash
cd ~/agent
export AGENT_API_KEY=$(grep HERMES_CUSTOM_127_0_0_1_20130_API_KEY ~/.hermes/.env | head -1 | cut -d= -f2 | tr -d '"')
python -m agent "list 3 planet terdekat matahari, simpan ke ~/agent/sandbox/planets.txt"
python -m agent --list                              # semua task
python -m agent --resume <task_id>                  # lanjut dari checkpoint
python -m agent --budget-tokens 20000 --budget-iters 8 --timeout 120 "..."
```

## Skill contract (the only requirement)

A skill is a single `.py` file in `skills/builtin/` or `skills/user/`:

```python
NAME = "my_skill"

def run(args, task):
    # args: dict (whatever the planner put in step["args"])
    # task: dict — read-only except task.setdefault("artifacts", []).append(path)
    # return: {"ok": bool, ...arbitrary fields, "saved_to" if wrote a file}
    ...

def register(reg):
    reg(NAME, run)
```

Auto-loaded by `core/registry.py:auto_load()`. No manifest, no YAML, no signup. Drop the file in and it works.

## Built-in skills (v0.4)

| Skill | Use for | Key args |
|-------|---------|----------|
| `code` | generate/refactor/debug/explain source | `op, lang, prompt, file?, save_to?` |
| `scraping` | fetch + extract a single URL | `url, selector?, max_chars?, extract?` |
| `web_research` | multi-URL research + summary | `urls, question, save_to?` |

Add more by copying any of these as a template.

## Built-in tools (in `core/executor.py`)

| Tool | Purpose |
|------|---------|
| `shell` | run whitelisted shell commands |
| `file_read` | read a file (policy-gated) |
| `file_write` | write/append a file (policy-gated, registers as artifact) |
| `web_fetch` | raw HTTP GET/POST |
| `ask_user` | placeholder for Telegram interaction |

## Critical pitfalls (all hit during v0.1 → v0.6)

### 1. Skill plugins MUST use 3-dot relative imports, not 2

If `agent.py` (or `__main__.py`) is in the root, importing it as `import agent` makes `agent` a **module**, not a package — `from ..core import` then fails with `'agent' is not a package`. Two fixes, do both:

- Rename the CLI file to `__main__.py` and add an empty `__init__.py` at the root. Now `python -m agent` works AND `agent` is a package.
- In every skill, use `from ...core import registry, router, policy` (three dots, not two — two dots resolves to `agent.skills`, not `agent`).

**Symptom:** `ImportError("cannot import name 'registry' from 'agent.skills' (path/to/agent/skills/__init__.py)")`

**Secondary symptom (silently swallowed):** `auto_load()` catches the exception and prints `[registry] agent.skills.builtin import fail: ModuleNotFoundError(...)` to stderr — the loop continues with **0 skills registered**. The agent then says "no skill matched" on every step. Always log registry load counts at startup and assert `len(skills) > 0` before planning.

### 2. The evaluator's LLM will lie about side effects

When the goal says "simpan ke file" and the step produced the right content but didn't write to disk, the LLM evaluator often returns `done:true` with a "well, the content is correct" reason. **Override it.**

In `evaluator.py`, after parsing the LLM response, sanity-check. Use the **broader** `wants_artifact_creation` flag, not just `wants_file` — otherwise goals like "buat script foo.py" (no `simpan ke` keyword) still slip through:

```python
goal_lc = task["goal"].lower()
wants_file = any(k in goal_lc for k in ("simpan ke", "save to", "tulis ke", "write to", "simpan di", "store in"))
wants_artifact_creation = wants_file or any(k in goal_lc for k in (
    "buat script", "buat file", "create file", "create script", "write file",
    "tulis script", "simpan hasil", "save hasil", "tulis ke file",
    ".py", ".txt", ".md"
))
if wants_artifact_creation and not task.get("artifacts") and parsed.get("done"):
    parsed["done"] = False
    parsed["next"] = "continue"
    parsed["reason"] = "override: goal mentions file output but artifacts empty"
```

The LLM can also lie the **other** direction — return `retry` even when the step succeeded and the file was written (BUG-009). For that, add the anti-stuck fail-streak check (sanity #4 in pitfall #13) and the early-stop heuristic (sanity #2 in pitfall #13), both gated by `wants_artifact_creation` to avoid premature stops.

This is the difference between "agent says done" and "agent actually done."

### 3. The planner LLM forgets `save_to` — auto-inject from the goal

For the `code` skill, when the LLM planner fills `args={"lang":..., "op":...}` but omits `save_to`, the skill writes to `~/agent/sandbox/<llm_invented_name>.py` instead of where the user asked. Fix in `executor.py:_exec_skill`:

```python
if "save_to" not in args:
    m = re.search(r"(?:simpan (?:ke|di)|save to|tulis ke|write to)\s+([~/][\w./-]+\.\w+)", task.get("goal", ""))
    if m:
        args = dict(args); args["save_to"] = m.group(1)
```

### 4. Auto-reload vs restart — DB edits vs skill edits

- Editing `state/*.json` while a task is running: the task re-reads its own file only on resume; live edits during a run won't change in-memory state.
- Editing `skills/builtin/*.py`: agent doesn't hot-reload — restart the task (`--resume`).
- Editing `core/*.py`: full restart required, and **in-progress tasks are corrupted** (their checkpoint state references old function signatures). Always resume from the last good checkpoint after editing `core/`.

### 5. The routerku is async-by-default; pass `stream=false` for tools

`core/router.py` calls `chat()` with `stream=False` (synchronous). If you wire up a streaming client, the executor's `obs["content"]` extraction breaks because the body is SSE. Either consume the SSE yourself in the router and return the final message, or stick to non-streaming for the agent path.

### 6. `providerNodes` without `providerConnections` is silent

When adding a new provider prefix to a combo, **also** add a connection row — routerku's `loadDb` skips orphaned nodes (node exists in `providerNodes` but `connections.length === 0`). Auto-reload picks up the new connection in ~3s, no restart needed. See skill `llm-router-failover`.

### 7. Free-model LLM quality varies per request

The Free-All combo hits different upstreams per call. Sometimes the `code` skill returns a perfectly-factorial function, sometimes it returns `def hello_world()`. **This is not an agent bug** — it's the underlying model. Workarounds for production use:
- Add a verification step in the skill ("does the function compile?") before declaring ok.
- Re-plan on eval failure rather than giving up.
- Use a stronger model (e.g. `fk/claude-sonnet-5`) for code tasks; `Free-All` for simple factoid reasoning.

### 8. Policy allowlist must be regex-anchored on the command verb, not the full path

`core/policy.py` typically runs a check like `cmd.startswith(prefix)` against a hardcoded list (`du`, `df`, `ls`, ...). When you add `timeout`, `wc`, `stat`, `head`, `tail`, the agent's shell tool fails with "blocked" even though the binary is harmless. **Pattern:** match the first whitespace-delimited token of the command with `re.match(r"^(timeout|wc|stat|head|tail|du|df|ls|cat|file|stat|find|grep)\b", cmd)` — `\b` ensures `du` doesn't match `dummy_tool`. Allowlist the verbs you trust, not the full command strings. See `references/policy-patterns.md` for the v0.5 working set.

### 9. Evaluator+loop drops the action dict if `append_history` is called too early

If `core/loop.py` calls `memory.append_history(task, step, obs, action)` **before** the evaluator runs, then `action` is always `None` in the per-step log. Symptom: the task completes, `step.result = {}` or `action: None` shows up, and you can't tell from history whether the evaluator wanted to continue/replan/stop.

**Pattern:** `append_history` is the LAST thing in the iteration. Order in `loop.run()`:

```python
obs = execute(step)             # 1. run the step
action = evaluate(obs, step)    # 2. get the action dict
memory.append_history(task, step, obs, action)   # 3. record with the real action
```

If `action` ends up `None` despite this order, you're probably calling `append_history` in two places (loop + evaluator). Pick one. The recommended location is in `core/evaluator.py:evaluate()` and `_rule_fallback()` — that way the action is captured right before return, and the loop stays clean.

This is a **low-priority** fix; do it only when you're tired of debugging with no history. (BUG-005, fixed in v0.5.)

### 10. Planner LLM JSON parse fallback can swallow the plan silently

If the planner's LLM returns malformed JSON (very common on free models, especially with reasoning_content fields embedded), `planner.py:make_plan` falls back to a single-step `fallback plan` derived from the LLM content's first 1500 chars. That content is then executed as the step's `prompt` argument. Works for trivial goals; for multi-step goals it produces a single mega-step that often times out or hits the budget. **Fix:** when the parser fails, log the raw response (truncated) and attempt a one-shot repair via a second LLM call (`"fix this into valid JSON: {raw}"`) before falling back. If the second call also fails, THEN emit the fallback — and bump the iter budget by 1 to compensate.

### 11. Telegram: same token = 409, separate token = full bidirectional OK

If you run a Telegram bot via long-polling (`getUpdates`) while the Hermes gateway is already polling the **same** bot token, one of them gets 409 Conflict. Options:
- **Push-only** (`sendMessage` only, no polling) for status notifications when sharing the token.
- **Separate bot token** for the agent bot → full bidirectional long-polling works fine alongside the Hermes gateway. VERIFIED 2026-09-04: agent bot `@QMybotai_bot` (token in `~/.hermes/agent_bot_token`, chmod 600) long-polls while Hermes gateway polls its own bot. The agent bot's `_load_env()` only fills env vars that are unset, so start it with `TELEGRAM_BOT_TOKEN=$(cat file)` exported by a launcher script — do NOT put the agent token in `~/.hermes/.env` (that file belongs to the Hermes gateway bot).

Do NOT try to multiplex `getUpdates` offsets on one token — it's racy and the gateway will win.

### 12. `loop.run()` requires a Reporter — there is no `quiet=True` kwarg

`core/loop.py:run(task, rep)` takes the Reporter as a **required positional** argument. There's no `quiet` flag. Calling `loop.run(task)` from a script raises `TypeError: run() missing 1 required positional argument: 'rep'`. Always construct a Reporter first:

```python
from core import loop, reporter
from core.memory import new

t = new("goal here", budget_iters=4, budget_tokens=50000)
loop.run(t, reporter.Reporter(t))   # stdout only, Telegram no-op if TG_BOT_TOKEN unset
```

The Reporter silently no-ops on Telegram if `TG_BOT_TOKEN` is missing — it's safe to construct in any context. The CLI's `__main__.py:main()` builds one for you; for ad-hoc scripts and tests, build it inline. (BUG-008, documented in v0.5.)

### 13. `is_goal_done()` checks the wrong field, and the canonical 6-sanity-check pattern

The loop's early-exit at `core/loop.py:34` (`if is_goal_done(task): break`) and the evaluator's `__done__` field are on **different objects**. `__done__` is set on the action dict (`{"stop": True, "__done__": True, "reason": "..."}`), not on obs. The original `is_goal_done()` scanned `obs`, so it never saw the early-stop. (BUG-010.) Fix: scan `task["history"][i]["action"]` and accept both `__done__=True` and the heuristic pattern `stop=True + "early-stop" in reason`.

After v0.6, the canonical evaluator has **six** sanity checks, applied in this order — each is independent:

1. **`wants_file + no artifact → done=False`** (pitfall #2). Catches the LLM claiming done without checking disk.
2. **`shell ok + stdout non-empty + goal doesn't need file → early-stop`**, **gated by `wants_artifact_creation`** (BUG-012). Without the gate, mkdir stdout triggers a premature stop before the `file_write` step. The `wants_artifact_creation` flag is broader than `wants_file` — it matches `buat script`, `buat file`, `create file`, `write file`, `tulis ke file`, and any goal containing a file extension (`.py`, `.txt`, `.md`).
3. **`shell ok + redirect + file on disk → early-stop`** (pitfall #14 / BUG-014). Critical for `echo x > file` where `obs.content=""` but the file exists.
4. **2x fail streak (`obs.ok=False`) → force replan** (anti-stuck). Without this, `find /data` burning perm-denied retries consumes the whole budget.
5. **Reason-keyword check** — if the LLM's own reason contains "belum ada / no output / tidak ada / kosong" but it returned `done=true`, override to `replan` (BUG-013). Free models sometimes close-out politely while admitting incompleteness. Keywords:
   ```python
   ADMITS_INCOMPLETE = (
       "belum ada", "belum selesai", "tidak ada", "no output", "no artifact",
       "no result", "no data", "not yet", "belum ditampil", "kosong",
       "tidak berhasil", "gagal menampilkan", "tidak ditemukan", "no match"
   )
   ```
6. **`kind=think` step → never done** — force `continue` (BUG-014). When the planner emits `kind=think, name=think`, the executor just generates text; the LLM evaluator can hallucinate "done" because the text was relevant. For think steps, `done=true` is almost always wrong.

**Field-name gotchas** (all bit v0.6 patches):
- `step.kind` is set to `"tool"` by executor; the tool name is in `step.name` (e.g. `"shell"`). Heuristics must check `step.get("name") == "shell"`, not `step.get("kind")`.
- Shell `obs.output` is the stdout, not `obs.content`. The evaluator prompt extractor must include `output` as fallback: `content_preview → content → output → error → _raw`.
- `is_goal_done()` was originally checking `obs.__done__`. `__done__` is on the action dict. Scan `task["history"][i]["action"]` instead.

### 14. Termux path resolution: `/tmp` is read-only, `/data` is perm-denied, and the regex must be anchored

On Termux/Android, `/tmp` is owned by `system` and not writable for `u0_a*` users. `/data` is the same (other apps' private storage). The real writable temp is `$TMPDIR` (`/data/data/com.termux/files/usr/tmp`); the real user home is `$HOME` (`/data/data/com.termux/files/home`). Goals that say "simpan ke /tmp/foo.txt" or "cari file di /data" are unsatisfiable as written. (BUG-015 + BUG-016.)

**Fix:** add `_resolve_path()` in `core/executor.py` and apply it to:
- `tool_file_write(path=...)`
- `tool_file_read(path=...)`
- `tool_shell(cmd=...)` — regex-substitute `/tmp` and `/data` tokens in the cmd string BEFORE `shlex.split`
- `tool_shell` retry on `Permission denied` stderr
- `log_analyzer(source=...)`
- `_exec_think(save_to=...)`

Also add `$TMPDIR` to `policy.DEFAULT["write_paths"]` — otherwise the resolved path is still denied by the policy layer.

**Critical regex pitfall (the part that bit hardest):** do NOT use `cmd.replace("/data", home, 1)`. `$HOME` is itself `/data/data/com.termux/files/home`, so substring-replace double-substitutes any cmd that already contains a `$HOME`-expanded path, producing paths like `/data/data/com.termux/files/home/data/data/com.termux/files/home/foo`. Use anchored regex with negative lookbehind/lookahead:

```python
cmd = re.sub(r'(?<![/\w])/data/(?!data/com\.termux)', home + "/", cmd)
cmd = re.sub(r'(?<![/\w])/data(?![/\w])', home, cmd)
```

The same applies to the **ground truth checker** in `eval_v2.py` — it must use `_resolve_path()` too, otherwise the agent writes to `$TMPDIR/agent_test/x.py` but the checker looks at `/tmp/agent_test/x.py` and reports `file_exists=False` (BUG-018). Always check both paths in the GT checker.

`toybox find` (Termux's default) lacks `-printf`. The smart-fallback "Cari file" branch in `core/planner.py` must chain `find -printf` with a `ls -la | sort` fallback (BUG-017), or "find largest file" tasks return empty stdout.

## Self-extension (v0.7) — the agent writes its own tools

`core/extender.py` adds a `learn_tool` built-in tool: when a goal needs a capability that doesn't exist, the planner emits a `learn_tool` step BEFORE the step that uses it. Flow: LLM generates a skill `.py` (contract: `fn(args, task) -> dict` + `register()`) → written to `skills/user/<name>.py` → `py_compile` → cache-busted import → **smoke test with test_args** → on failure the error + old code go back to the LLM (max 3 attempts) → success = permanently registered, survives restarts (auto_load picks it up).

Four pitfalls that took real debugging (full detail in `references/self-extension-v07.md`):

1. **Smoke test must check the VALUE of `ok`, not just its presence.** `"ok" in obs` passes for `{"ok": False, "error": "name 're' is not defined"}` — a broken skill gets registered as success. Raise on `not obs.get("ok")` so the self-fix loop actually sees the failure.
2. **LLM code forgets stdlib imports** (`re`, `from collections import Counter`). Retrying via LLM wastes 3 attempts on the same bug — add a deterministic `_auto_fix_imports()` pre-pass: regex-scan usage (`\bre\.`) vs imports, insert missing ones after the docstring. Special-case `Path(` → `from pathlib import Path`, `Counter(` → `from collections import Counter`.
3. **Planner hallucinates skill arg names** (`{action, input}` vs the skill's `{mode, text}` contract) → 3 identical failures, budget burned. Fix: derive each skill's arg spec from its source (`re.findall(r'args\.get\(["\'](\w+)["\']', src)`) at auto_load time, store in `registry._skill_spec`, and render it into the planner prompt: `skills (nama(args_wajib)): [base64_tool(mode,text), ...]`. Persisted via source-scan, so it survives restarts with no manifest.
4. **Planner writes literal placeholders** for runtime values: `content: "HASIL_DARI_STEP_SEBELUMNYA"`, `REPLACE_WITH_RESULT`, `<hasil>` — and the evaluator sometimes still says done, so garbage lands on disk. Fix deterministically in executor: `_is_placeholder()` (covers SCREAMING_CASE via `s.isupper()` + keyword list — the isupper guard prevents false-positives on real base64/`HTTP 200 OK` strings) → substitute `_last_success_result(task)` (walks history newest-first for `obs.ok` payload: result/content/output/data/body). Apply in BOTH `file_write.content` AND inside `shell.cmd` (planner puts placeholders in heredocs/echo too). Also support `think` steps with `args.from_history: true` → injects a compact history digest into the prompt.

Also inject a live capability snapshot into `make_plan` AND `re_plan` user messages (`_caps_line()`: tools + skills-with-specs + 'if missing → learn_tool'). Without it the planner re-invents existing skills or hallucinates args.

## Human gates & interrupt (v0.6)

Loop supports three pause statuses — `awaiting_approval` (plan mode: `/plan <goal>` plans then returns), `awaiting_step` (`/agent --step <goal>`: gate before every step), `awaiting_permission` (executor returns `policy_deny: true` → gate instead of silent failure). Each gate: thread exits, state saved to disk, bot sends the pending plan/step/deny detail + response commands (`/approve <id> [step]`, `/allow <id> <read|write|exec> "<pattern>"`, `/deny <id>`). Approve = mutate state + respawn thread (`_resume`). Grants persist per-task in `task["grants"]` and flow into `policy.is_path_allowed(..., grants=)` / `is_command_allowed(cmd, grants=)`.

Interrupt: `/cancel` writes `status: cancel_requested` to the state file; the loop re-reads its own file from disk at the top of every iteration and at checkpoint time (before `memory.save`, so it never clobbers a user cancel). Prompt queue: while any task thread is alive, plain text and new `/agent` goals go into a `deque(maxlen=20)` and auto-drain in `_after_task` (re-parse `/plan`/`--step` prefixes when draining, or the queued task silently loses its mode).

## Verifying it works

```bash
# 1. Sanity — single factoid
python -m agent "jawab 1 kata: planet terdekat matahari" --budget-iters 4

# 2. Side-effect — write a file
python -m agent "list 3 planet, simpan ke ~/agent/sandbox/planets.txt" --budget-iters 8

# 3. Multi-step via skill
python -m agent "panggil skill code untuk generate factorial(n), simpan ke ~/agent/sandbox/factorial.py" --budget-iters 8

# 4. Inspect state
python -m agent --list
ls ~/agent/state/   # checkpoints
ls ~/agent/sandbox/ # artifacts
cat ~/agent/logs/<task_id>.log  # per-step trace
```

## What's intentionally NOT here

- **Telegram inter-activity** (`ask_user` blocking) — placeholder only; full integration needs bidirectional bot + a webhook from Telegram to the agent process.
- **Sandboxed subprocess** for tools — currently trust-based via `core/policy.py` whitelist. A real sandbox needs chroot/namespace on Termux (often impossible without root) or a Docker container.
- **Concurrent agents** — single-process loop. Multi-agent needs a queue + worker pool.
- **Persistent vector memory** — only flat JSON state. RAG/episodic memory is a v1.0 feature.

## Files

- Reference impl: `~/agent/`
- Skills dropped in: `~/agent/skills/builtin/`, `~/agent/skills/user/`
- Checkpoints: `~/agent/state/`
- Logs: `~/agent/logs/<task_id>.log`
- Provider: `~/routerku/` (see `llm-router-failover`)

## References

- `references/policy-patterns.md` — v0.5 working set of allowlisted commands + the regex pattern
- `references/termux-runtime.md` — verified Termux/Android runtime facts (routerku :20130, Free-Kombo/Free-All combos, model aliases, free model matrix)
- `references/known-bugs.md` — bug log per version with reproduction, root cause, fix
- `references/eval-benchmark.md` — 8-task benchmark structure, per-task ground truth checker, anti-loop heuristic, interpretation table

## See also

- `llm-router-failover` — provider routing + auto-reload DB
- `multi-provider-failover` — provider health + cooldown values
- `software-development/spec-driven-development` — write the goal spec first, then run the agent
- `software-development/planning-and-task-breakdown` — manually break goals into steps the planner can re-use
- `references/self-extension-v07.md` — learn_tool pipeline detail, placeholder-resolve regexes, gate state machine, Termux:API reality
