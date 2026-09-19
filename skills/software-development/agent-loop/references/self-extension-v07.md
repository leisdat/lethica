# Self-extension v0.7 — verified session detail (2026-09-04, ~/agent)

## learn_tool contract (core/extender.py)

Generator system prompt requires EXACTLY:
```python
NAME = "<skill>"
def <skill>(args, task): ...   # returns {"ok": bool, ...}
def register(reg): reg(NAME, <skill>)
```
stdlib-only, imports at top, robust to missing args (return ok False, never raise).

Smoke test gate order (each failure → next attempt with error+code fed back):
1. `"def register" in code` else retry
2. `_auto_fix_imports(code)` deterministic patch BEFORE compile
3. `py_compile.compile(doraise=True)`
4. cache-busted import: pop `agent.skills.user.<n>` AND `skills.user.<n>` from sys.modules, `importlib.invalidate_caches()`, try both import styles
5. `register()` into a temp dict, call fn with test_args
6. result must be dict, have `"ok"`, AND `ok` must be truthy ← the bug that bit: presence-check alone registered a broken skill
7. only then `registry.register_skill(name, fn, spec=...)`; on total failure `path.unlink()` the broken file

## _auto_fix_imports

```python
_STDLIB_HINTS = {"re": r"\bre\.", "json": r"\bjson\.", "os": r"\bos\.", "sys": r"\bsys\.",
    "math": r"\bmath\.", "random": r"\brandom\.", "time": r"\btime\.",
    "datetime": r"\bdatetime\.", "pathlib": r"\bPath\(|\bpathlib\.",
    "subprocess": r"\bsubprocess\.", "hashlib": r"\bhashlib\.", "shutil": r"\bshutil\."}
# bare-name usages needing from-imports:
_FROM_IMPORTS = [(r"\bCounter\(", r"from collections import[^\n]*\bCounter\b", "from collections import Counter"),
    (r"\bdefaultdict\(", ..., "from collections import defaultdict"),
    (r"\bdeque\(", ..., "from collections import deque"),
    (r"\bdatetime\.|\bdate\.|\btimedelta\(", ..., "from datetime import datetime, timedelta")]
```
Insert header after leading docstring (`re.match(r'\s*("""|\'\'\')[\s\S]*?\1\n', code)`), else top. pathlib → `from pathlib import Path`, never `import pathlib` (code uses bare `Path(`).

## Skill arg-spec → planner prompt

- `registry.register_skill(name, fn, spec=None)`; `_skill_spec` dict; `get_skill_spec(name)`.
- learn_tool passes `spec = sorted(set(test_args) | set(re.findall(r'args\.get\(["\'](\w+)["\']', code)))`.
- `registry._derive_spec(f, m)` re-derives from source on every `auto_load()` → persists across restarts with zero manifest files. Verified: all 8 skills got correct specs after fresh process start.
- `planner._caps_line()` renders `base64_tool(mode,text)` style list into BOTH make_plan and re_plan user messages + "args PERSIS sesuai nama argumen" instruction.

## Placeholder auto-resolve (executor)

```python
_PLACEHOLDER_RE = re.compile(r"^(?:REPLACE_WITH_\w+|<[^>]{1,60}>|\{\{[^}]{1,80}\}\}|TBD|xxx+|TODO.*)$", re.I)
_SCREAM_KEYWORDS = ("HASIL","RESULT","OUTPUT","VALUE","GANTI","ISI","TBD","PLACEHOLDER","XXX")
def _is_placeholder(content):
    s = str(content).strip()
    return bool(_PLACEHOLDER_RE.match(s)) or (s.isupper() and any(k in s for k in _SCREAM_KEYWORDS))
```
- `s.isupper()` guard is what prevents false positives: real base64 `c2hhZG93Y29yZQ==` and `HTTP 200 OK` contain lowercase → safe. Unit-tested 10/10 cases.
- Pitfall hit: first attempt used `[A-Z][A-Z_ ]*HASIL...` regex WITHOUT isupper + IGNORECASE → matched nothing (first char class ate the H) and would have false-matched. The isupper+keyword approach is the durable one.
- `_last_success_result(task)`: reversed history, first `obs.ok` truthy, payload key priority `result > content > output > data > body`, dict → json.dumps.
- Applied in `file_write.content` AND `shell.cmd` (regex-search the whole command for `HASIL_[A-Z0-9_]+` / `*_RESULT*` / `REPLACE_WITH_\w+` tokens that `.isupper()`, `cmd.replace(token, last)`). Shell case matters: planner wrote `echo "$(cat <<'EOF' HASIL_DARI_STEP_SEBELUMNYA EOF)" > file` — file_write guard alone missed it, file got the literal placeholder while evaluator said done.
- If placeholder found but history has no success yet → return ok False with instruction to reorder steps (don't silently write garbage).

## think from_history

`step.args.from_history: true` → `_exec_think` prepends `_history_context(task)` (last 6 entries: `[kind:name] ok=… → payload[:400]`) + "Jawab HANYA nilai/teks yang diminta". This is the LLM-side escape hatch; placeholder-resolve is the deterministic one.

## Gate/interrupt state machine (loop.py)

- `GATE_STATUSES = ("awaiting_approval","awaiting_step","awaiting_permission")` — bot checks `agent_loop.GATE_STATUSES` to decide notify-vs-finalize.
- planning: `status="planning"` → run() makes plan, sets awaiting_approval, RETURNS (thread exits; no parked thread waiting).
- step gate: `task.step_approval` + `not task._step_ok` → awaiting_step + `_pending_step=queue[0]`. `/approve <id>` clears step_approval (auto-rest); `/approve <id> step` keeps gating.
- permission gate: executor deny paths return `{ok:False, policy_deny:True, deny_kind, deny_target, error}`; loop converts to awaiting_permission + `_deny_info`, re-inserts step at queue head on /allow.
- grants: `task["grants"] = [{"type":"read|write|exec","pattern":...}]`; policy functions take `grants=None` kwarg; exec grant = prefix match on command string; DENY_PATTERNS still checked FIRST (grants can't override rm -rf / etc).
- interrupt: `/cancel` → if thread alive write `cancel_requested` to disk (loop re-reads own state file at top of iteration AND before final save to avoid clobbering the cancel); if thread dead (gate) → direct `stop`.
- queue drain: `_after_task` re-parses `/plan ` and `--step` prefixes from queued text — without this a queued plan-mode task runs full-auto.

## E2E results (all on Free-All combo, minimax-m3 answering)

1. text_stats: attempts=2 (attempt1 missing `import re` → smoke caught it post-fix), tokens 2030
2. base64_tool: created via learn_tool inside a full loop run, encode+decode verified in fresh process
3. Final goal 'encode shadowcore → save to b64.txt': STATUS done iter 4, FILE `c2hhZG93Y29yZQ==` (after placeholder-resolve + arg-spec fixes; before those: iter 8 budget_exhausted / garbage file)
4. android_device probe: battery 80%, model 2201117PG, soc mt6781, 8 cores, Android 13, errors {}

## Termux:API reality (android_device skill)

CLI pkg `termux-api` alone is NOT enough — sensor/wifi/location commands print "Termux:API is not yet available…" when the companion APK isn't installed. Working CLI-only: battery-status, volume, torch, clipboard, vibrate, tts, notification, telephony. Screenshot: `/system/bin/screencap -p <path>` works without root. The skill detects the missing-app string and returns a clear install hint rather than a raw error.
