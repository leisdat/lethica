# `~/agent` — known bugs log

Per-version log of bugs found, root cause, and fix. Use as a quick reference when the agent misbehaves in a known way.

## v0.6 (2026-09-04) — current

### BUG-010: `is_goal_done()` checks the wrong field

- **Symptom:** After sanity check 2 fires (`stop=True, __done__=True, reason="heuristic early-stop..."`), the loop's `if is_goal_done(task)` check at line 34 still returns False, so the loop re-runs the planner instead of breaking. The task then either replans or hits budget.
- **Impact:** Tasks that should finish in 1-2 iters burn the full budget. The user's "fix" in patch v0.5 (adding early-stop to evaluator) doesn't fully take effect because `is_goal_done` doesn't see it.
- **Root cause:** `is_goal_done()` was looking at `task["history"][i]["obs"].get("__done__")`, but `__done__` is set on the **action** dict, not the obs. So the early-stop decision was correctly recorded in action but invisible to `is_goal_done`.
- **Fix:** scan `task["history"][i]["action"]` instead. Accept both `__done__=True` and the heuristic pattern `stop=True + "early-stop" in reason`:

  ```python
  def is_goal_done(task):
      for x in reversed(task.get("history", [])[-5:]):
          act = x.get("action")
          if isinstance(act, dict):
              if act.get("__done__"):
                  return True
              if act.get("stop") and "early-stop" in act.get("reason", ""):
                  return True
      return False
  ```
- **Status:** PATCHED in v0.6.

### BUG-011: evaluator heuristic 2 never fires because `step.kind != "shell"`

- **Symptom:** Eval log shows shell step with stdout non-empty, `obs.ok=True`, but evaluator does not declare done. The task proceeds to next iter instead of stopping. This is the inverse of BUG-009 — the LLM is *too* conservative, not too liberal.
- **Impact:** Tasks that should finish in 1-2 iters take 4-5. Wasted tokens.
- **Root cause:** Sanity check 2 checked `step.get("kind") == "shell"`, but the executor writes `step.kind = "tool"` and the tool name in `step.name = "shell"`. The check never matched, so the heuristic never fired. Same gotcha applies to sanity check 3 (redirect file check).
- **Fix:** check `step.get("name") == "shell"`, not `step.kind`. Also extract stdout from `obs.output` (not just `obs.content`) — shell tool returns stdout in the `output` field, while file_read/skill results go to `content`:
  ```python
  stdout = (obs.get("content") or obs.get("output") or obs.get("_raw") or "").strip()
  ```
- **Status:** PATCHED in v0.6.

### BUG-012: heuristic 2 premature-stops after `mkdir` step

- **Symptom:** Goal "Buat script reverse_string.py di /tmp/agent_test/" — iter 1 runs `mkdir -p /tmp/agent_test`, succeeds with stdout `"mkdir: created directory '/tmp/agent_test'"`, evaluator returns `done=True, reason="heuristic early-stop: shell ok + stdout N chars"`. Loop ends. But no file was written.
- **Impact:** GT checker finds no `reverse.py` despite `status=done`. False positive: agent claims done without producing the artifact.
- **Root cause:** Heuristic 2 ("stdout non-empty → done") was too aggressive. It fired on any shell step that produced stdout, including setup steps like `mkdir`. The LLM intent was a multi-step plan (mkdir → file_write → verify), but the heuristic collapsed it to 1 step.
- **Fix:** add a `wants_artifact_creation` flag (broader than `wants_file`) and gate heuristic 2 on it:

  ```python
  wants_file = any(k in goal_lc for k in ("simpan ke", "save to", "tulis ke", ...))
  wants_artifact_creation = wants_file or any(k in goal_lc for k in (
      "buat script", "buat file", "create file", "create script", "write file",
      "tulis script", "simpan hasil", "save hasil", "tulis ke file",
      ".py", ".txt", ".md"
  ))
  if (not done and nxt in ("continue", "retry")
      and step.get("name") == "shell"
      and obs.get("ok")
      and not wants_file
      and not (wants_artifact_creation and not has_artifact)):
      # early-stop is safe
  ```
- **Status:** PATCHED in v0.6.

### BUG-013: evaluator LLM hallucinates `done=True` while admitting incompleteness in reason

- **Symptom:** Eval log shows `action={"stop": True, "__done__": True, "reason": "Setup parameter dan lokasi log Hermes agent sudah selesai dilakukan, namun goal adalah cek error 500 dalam 1 jam terakhir dan belum ada output/hasil pengecekan yang ditampilkan, serta tidak ada artifact yang menyimpan hasil."}`. The LLM literally wrote "belum ada output" in the reason but set `done=true`.
- **Impact:** LLM evaluator is unreliable for goals with vague success criteria ("cek", "analisis"). Agent stops without doing the work.
- **Root cause:** Free-Kombo LLM evaluator lacks ability to detect contradiction between its own `done` field and reason text. Sometimes returns done=true as a "polite" close-out.
- **Fix:** scan the reason text for admission keywords; if any present, override `done=False, nxt=replan`:

  ```python
  ADMITS_INCOMPLETE = (
      "belum ada", "belum selesai", "tidak ada", "no output", "no artifact",
      "no result", "no data", "not yet", "belum ditampil", "kosong",
      "tidak berhasil", "gagal menampilkan", "tidak ditemukan", "no match"
  )
  if done and any(k in (reason or "").lower() for k in ADMITS_INCOMPLETE):
      done = False; nxt = "replan"
      reason = f"override: LLM admit incomplete in reason: {reason[:120]}"
  ```
- **Status:** PATCHED in v0.6.

### BUG-014: `kind=think` step gets `done=True` from LLM evaluator

- **Symptom:** Goal "Cek log Hermes agent untuk error 500" — LLM planner emits `kind=think, name=think` step. LLM executor just generates a think-text response. LLM evaluator returns `done=true` because the think text "identifies the path" and "is relevant". Loop ends. No actual log check performed.
- **Impact:** Goals with vague "Cek" / "Analisis" wording get false-done at the first think step.
- **Root cause:** LLM evaluator conflates "produced relevant text" with "goal achieved". For `kind=think` steps, there is no tool side-effect, so `done=true` is almost always wrong.
- **Fix:** never let `kind=think` step declare done; force `nxt=continue`:
  ```python
  if done and step.get("kind") == "think":
      done = False
      nxt = "continue"
      reason = f"override: think step bukan action konkret, lanjut ke step berikutnya"
  ```
- **Status:** PATCHED in v0.6.

### BUG-015: Termux `/tmp` is read-only — all `file_write` to `/tmp/x` fail silently

- **Symptom:** `file_write path="/tmp/agent_test/foo.py"` returns `{"ok": False, "error": "policy deny: write /tmp/agent_test/foo.py"}` because `/tmp` is not in `write_paths` and is also not writable for Termux users. Goal says "simpan ke /tmp/foo.txt" — agent has no way to comply.
- **Impact:** Every benchmark task that mentions `/tmp` fails the file_write step.
- **Root cause:** On Termux/Android, `/tmp` is a shared tmpfs owned by `system`; `u0_a*` users have no write access. The actual user-writable temp is `$TMPDIR` (`/data/data/com.termux/files/usr/tmp`).
- **Fix:** add `_resolve_path()` in `core/executor.py` and apply it to:
  - `tool_file_write(path=...)`
  - `tool_file_read(path=...)`
  - `tool_shell(cmd=...)` — regex-substitute `/tmp` tokens in the cmd string
  - `tool_shell` retry on `Permission denied` (also for `/data`)
  - `log_analyzer(source=...)`
  - `_exec_think(save_to=...)`

  Also add `$TMPDIR` to `policy.DEFAULT["write_paths"]`:
  ```python
  "write_paths": [str(HOME / "agent" / "sandbox"),
                  str(HOME / "agent" / "state"),
                  str(HOME / "agent" / "logs"),
                  "/data/data/com.termux/files/usr/tmp"],  # $TMPDIR
  ```
- **Status:** PATCHED in v0.6.

### BUG-016: Termux `/data` is permission-denied — `find /data` always fails

- **Symptom:** `find /data -type f -name "*.log"` returns `find: '/data': Permission denied`. The agent can't read top-level `/data` (other apps' private storage). Goals like "Cari 5 file .log terbesar di /data" are unsatisfiable as written.
- **Impact:** T3 benchmark task fails. More importantly, the retry handler in tool_shell re-runs the same failing command 5 times burning budget.
- **Root cause:** Same as BUG-015 — Termux sandbox. `/data` is perm-denied at top level; only `/data/data/com.termux/...` is readable for the user.
- **Fix:** auto-substitute `/data` → `$HOME` (`/data/data/com.termux/files/home`) at the same call sites as BUG-015. **Critical:** use anchored regex, NOT `str.replace("/data", home, 1)`:

  ```python
  # WRONG: cmd = cmd.replace("/data", home, 1)
  #        $HOME is /data/data/com.termux/files/home → first /data in cmd
  #        gets replaced even when cmd already contains $HOME-expanded path → double-substitution
  #        produces /data/data/com.termux/files/home/data/data/com.termux/files/home/foo
  cmd = re.sub(r'(?<![/\w])/data/(?!data/com\.termux)', home + "/", cmd)
  cmd = re.sub(r'(?<![/\w])/data(?![/\w])', home, cmd)
  ```

  Also fix the planner's smart-fallback: the "Cari file" branch should default to `$HOME` as the search base, not `/` or `/data`.
- **Status:** PATCHED in v0.6.

### BUG-017: toybox `find` lacks `-printf` — smart-fallback returns empty stdout

- **Symptom:** Goal "Cari 5 file .log terbesar di /data" — smart-fallback emits `find / -type f -name '*.log' -printf '%s %p\n' 2>/dev/null | sort -rn | head -5`. Output is empty. Ground truth fails (output len = 0).
- **Impact:** All "find largest file" tasks fail on Termux.
- **Root cause:** Termux ships with `toybox find` which doesn't support `-printf`. Only BusyBox/GNU find do.
- **Fix:** chain `find -printf` with a `ls -la | sort` fallback so the second path is used when the first returns empty:
  ```bash
  find $HOME -type f -name '*.log' -printf '%s %p\n' 2>/dev/null | sort -rn | head -5; \
  if [ -z "$(find $HOME -type f -name '*.log' -printf '%s %p\n' 2>/dev/null | head -1)" ]; then \
    find $HOME -type f -name '*.log' 2>/dev/null | xargs ls -la 2>/dev/null | awk '{print $5" "$NF}' | sort -rn | head -5; \
  fi
  ```
  Better: detect the busybox variant at startup and use the appropriate form. See `references/termux-runtime.md` for the detection snippet.
- **Status:** PATCHED in v0.6 (chained fallback).

### BUG-018: GT checker uses literal `/tmp/...` path while agent writes to `$TMPDIR/...`

- **Symptom:** Eval benchmark reports `T1: status=done, file_exists=False` even though the file was correctly written to `$TMPDIR/agent_test/reverse.py`. The agent and the checker disagree on what `/tmp` means.
- **Impact:** False-negative GT pass count. Hides real successes and makes patches look like regressions.
- **Root cause:** Symmetric to BUG-015 — the GT checker needs the same `_resolve_path()` as the agent. Without it, the checker looks at `/tmp/agent_test/reverse.py` which is a different directory from where the file actually lives.
- **Fix:** apply `_resolve_path()` in the GT checker for every `path` it tests:
  ```python
  from core.executor import _resolve_path
  for p in [Path("/tmp/agent_test/reverse.py"),
            Path(_resolve_path("/tmp/agent_test/reverse.py"))]:
      if p.exists() and "def reverse" in p.read_text():
          ok = True; break
  ```
  Always check both the goal-as-written path and the resolved path.
- **Status:** PATCHED in v0.6 (eval_v2.py updated).

## v0.5 (2026-09-04)

### BUG-005: history `action: None` for every step (was reported as "step.result={}")

- **Symptom:** Task completes correctly, artifacts present, but `history[i].action = None` in the per-task log. The user sees `step.result={}` and asks "fix bug dulu".
- **Impact:** Cosmetic; doesn't break the run. Post-mortem debugging is harder because the evaluator's decision (continue / replan / stop) is lost from history.
- **Root cause:** `core/evaluator.py` computed the action dict (e.g. `{"prepend": [{"kind": "replan", ...}]}`) and then **returned** — but the caller in `core/loop.py` had already invoked `append_history(task, step, obs, None)` **before** the evaluator was called. Order of operations in `loop.run()`: executor returns → `append_history(... action=None)` → evaluator runs → action computed but never recorded.
- **Fix:** move `append_history` to **after** the evaluator runs, so the action dict is available. Two locations in `core/evaluator.py`:
  1. `evaluate()` — call `memory.append_history(task, step, obs, action)` right before `return result`.
  2. `_rule_fallback()` — same fix; it also returns an action dict that the loop was discarding.

  Net effect: `history[i].action` now reflects the real evaluator decision (continue / replan / stop). Verified by running a 4-iter task and printing `t["history"][i]["action"]` — first action is now `{"prepend": [{"kind": "replan", "note": "..."}]}` instead of `None`.
- **Status:** PATCHED in v0.5.

### BUG-008: `loop.run()` raises `TypeError: run() missing 1 required positional argument: 'rep'`

- **Symptom:** Calling `loop.run(task)` from a script raises `TypeError`. Easy to assume `quiet=True` is the kwarg.
- **Impact:** Can't test the loop without Telegram. Every direct invocation crashes.
- **Root cause:** `core/loop.py:run(task, rep)` — the `Reporter` is required positional, not optional. There is no `quiet` kwarg.
- **Fix:** always construct a Reporter first:

  ```python
  from core import loop, reporter
  from core.memory import new
  t = new("goal here", budget_iters=4, budget_tokens=50000)
  loop.run(t, reporter.Reporter(t))
  ```

  If you only want stdout output (no Telegram push), just `Reporter(task)` — it auto-detects `TG_BOT_TOKEN` env and silently no-ops if absent.
- **Status:** DOCUMENTED in v0.5 (added pitfall #12 in SKILL.md).

### BUG-006: registry auto-load silently registers 0 skills

- **Symptom:** Agent says "no skill matched" on every step. No exceptions raised to the user. Stderr shows `[registry] agent.skills.builtin import fail: ModuleNotFoundError`.
- **Impact:** Total silent failure of the skill subsystem. The agent falls back to raw shell for everything.
- **Root cause:** `core/registry.py:auto_load()` catches the import exception (which is correct — one bad skill shouldn't kill the agent) but doesn't fall back gracefully. The next layer (`executor.py:_exec_skill`) doesn't check `len(registry.skills)` and assumes the registry has entries.
- **Fix:** in `__main__.py:main()` after the registry initializes:

  ```python
  skills = registry.list_skills()
  if not skills:
      print("[FATAL] no skills registered — check ~/agent/skills/builtin/ for ImportError", file=sys.stderr)
      sys.exit(2)
  ```

- **Status:** PATCHED in v0.5 (added startup assertion in `__main__.py`).

### BUG-007: shell tool returns "blocked" for harmless verbs

- **Symptom:** `python -m agent "cari 5 file .log terbesar di ~/"` fails on the `du` step. `executor` log: `policy blocked: du -sh /data/...`.
- **Impact:** Many legitimate inspection commands are blocked.
- **Root cause:** `core/policy.py` allowlist used `startswith` and was hardcoded to a small set; new verbs (`timeout`, `wc`, `stat`, `head`, `tail`) were never added.
- **Fix:** rewrite as `re.match(r"^({verbs})\b", first_token)` (see `references/policy-patterns.md`).
- **Status:** PATCHED in v0.5.

### BUG-009: evaluator LLM returns `retry` infinitely even when step succeeds — needs `rule_fallback` anti-loop

- **Symptom:** 8-task benchmark (`eval_v2.py`) — every task ends `eval 🔁 retry` for 4-5 iterations, then `⚠ budget/timeout habis`. Even when the file was created on iter 1. Log pattern: `iter 1: shell ok, output non-empty, eval 🔁 retry. iter 2: same shell, same output, eval 🔁 retry. ... iter 5: budget habis.`
- **Impact:** 0/8 success rate even with the v0.5 fixes for pitfalls #2, #14. The agent cannot complete ANY task reliably on Free-Kombo.
- **Root cause:** Free models (minimax-m3, glm-5.3) are biased toward "be thorough". When the step's `obs.ok=True` and `obs.content` non-empty, the evaluator LLM still returns `nxt=retry` with a vague reason ("need to verify"). The same step runs again with the same prompt, gets the same success, and the loop becomes idempotent. No progress, just budget burn.
- **Sub-bug:** when planner uses shell redirect (`echo x > /tmp/foo`), `obs.content=""` because the redirect swallows stdout. The LLM has no signal that the file was created.
- **Fix:** three parts, all in `core/evaluator.py`:
  1. **`_rule_fallback` anti-loop** — count `nxt=retry` actions in last 5 history entries. After 3 retries without progress, force stop with `__done__=True` (accept) or `False` (give up).
  2. **Sanity check 3** — `obs.get("redirected")` paths from executor. If any exist on disk, override `done=True`.
  3. **Sanity check 2 expansion** — if `obs.ok=True` + `obs.content` non-empty AND queue is empty (not retrying same step), override `nxt=continue` to make progress.
- **Test:** `eval_v2.py` re-run after fix → expected 5/8 (up from 0/8). The 3 remaining failures are T4 (think step has no `obs.ok` flag), T8 (log file path that doesn't exist in test env), and one marginal LLM-coherence case.
- **Status:** PATCHED in v0.5 (awaiting re-verification).

## v0.4 (2026-09-03)

### BUG-004: planner LLM returns content with reasoning_content prefix → JSON parse fails

- **Symptom:** Planner prints `step: fallback plan (LLM parse failed) raw='{"plan":[{"k...` and proceeds with a single mega-step derived from the raw content.
- **Impact:** Multi-step goals collapse to one step. Often hits budget.
- **Root cause:** GLM / DeepSeek return their reasoning content as part of the response body. The planner's `json_parse` tries to extract JSON but the prefix is reasoning text.
- **Fix:** in `core/planner.py:make_plan`, strip everything before the first `{` and after the last `}` before parsing. AND attempt a one-shot repair LLM call if parsing still fails. See pitfall #10 in SKILL.md.
- **Status:** PATCHED in v0.5.

### BUG-003: skill uses `from ..core import` instead of `from ...core import`

- **Symptom:** `ImportError("cannot import name 'registry' from 'agent.skills' ...")`.
- **Root cause:** When `__main__.py` is at the root and the agent is run as `python -m agent`, `agent` is a package, but the skill's two-dot relative import resolves to `agent.skills` (its parent), not `agent`. Need three dots.
- **Fix:** every skill: `from ...core import registry, router, policy`.
- **Status:** PATCHED in v0.4 (see pitfall #1 in SKILL.md).

## v0.3

### BUG-002: evaluator says `done: true` but no artifact exists

- **Symptom:** Goal says "simpan ke sandbox/x.txt", agent reports "done", but `ls sandbox/x.txt` returns nothing.
- **Root cause:** LLM evaluator returns `done: true` based on the step's stdout (which contains the right content) without checking the disk.
- **Fix:** in `core/evaluator.py`, sanity-check `task["artifacts"]` against `goal` text (see pitfall #2 in SKILL.md).
- **Status:** PATCHED in v0.3.

## v0.2

### BUG-001: planner LLM omits `save_to`, skill writes to default name

- **Symptom:** Goal says "simpan ke factorial.py", but the file lands at `sandbox/factorial_v2.py` (LLM-invented name).
- **Root cause:** Planner fills `args={lang, op, prompt}` but forgets `save_to`. Skill defaults to `sandbox/<llm-invented>.py`.
- **Fix:** in `core/executor.py:_exec_skill`, regex-extract `save_to` from the goal text and inject it. See pitfall #3 in SKILL.md.
- **Status:** PATCHED in v0.2.

## Reproducing any bug

```bash
# 1. Find the version
cd ~/agent && grep -r "version" __init__.py

# 2. List recent tasks
python -m agent --list

# 3. Read the failing task's log
cat ~/agent/logs/<task_id>.log

# 4. Reproduce
python -m agent "the same goal" --budget-iters 8
```

## Reporting new bugs

When you hit a new bug, append to this file with:
1. BUG-NNN identifier
2. Symptom (what the user saw)
3. Impact (severity)
4. Root cause (one sentence)
5. Fix (code or pointer)
6. Status (PATCHED / NOT YET PATCHED)
