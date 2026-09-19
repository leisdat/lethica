# Benchmarking a goal-driven LLM agent

How to measure whether `~/agent` (or any goal-driven agent loop) is actually working, not just running. The eval framework below was the basis of the v0.5 → v0.6 quality gate — every patch was verified against this benchmark before being declared "fixed".

## Why you need this

A single E2E test ("buat script reverse_string.py") only proves one path works. It does not catch:
- The evaluator being biased toward `done=True` (false positive — see pitfall #2 in SKILL.md)
- The evaluator being biased toward `retry` even on success (false negative — see pitfall #13 / BUG-009)
- The planner falling back to a single `think` step that never produces a tool call (pitfall #15)
- The shell tool's silent failure on redirect (pitfall #14)
- Token budget mis-allocation (some tasks need 8 iters, some need 4)
- The **premature early-stop** after partial success (e.g. `mkdir` succeeded, file not yet written, but stdout non-empty triggered `done=True`) — see "Premature early-stop" section below
- **Path mismatch** between what the goal says (`/tmp/foo`) and where Termux actually lets the agent write (`$TMPDIR/foo`) — false-negative ground truth if the checker uses the literal goal path

Benchmark with 5-8 diverse tasks reveals the failure modes; a single test hides them.

## Termux path resolution (CRITICAL for ground truth on Termux)

`/tmp` is read-only on Termux (it's a shared tmpfs across the system, and `u0_a*` users have no write). `/data` is perm-denied (other apps' private storage). The agent **must** auto-substitute these to `$TMPDIR` and `$HOME` respectively — and the **ground truth checker must do the same** or you'll see `file_exists=False` even when the file was correctly written.

The agent's `_resolve_path()` (in `core/executor.py`):

```python
def _resolve_path(p):
    s = str(p).strip()
    if s.startswith("~"): return str(Path(s).expanduser())
    if s.startswith("/tmp") or s == "/tmp":
        if not os.access("/tmp", os.W_OK):
            tmpdir = os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")
            return s.replace("/tmp", tmpdir, 1) if s != "/tmp" else tmpdir
    return s
```

The GT checker should apply the same function:

```python
from core.executor import _resolve_path

if tid == "T1":
    # cek di /tmp/agent_test/ (goal as written) DAN di $TMPDIR/agent_test/ (where agent actually wrote)
    for p in [Path("/tmp/agent_test/reverse.py"),
              Path(_resolve_path("/tmp/agent_test/reverse.py"))]:
        if p.exists() and "def reverse" in p.read_text():
            ok = True
            break
```

For `shell` commands, the substitution is regex-based (since the path appears as a token inside the cmd string, not as a Python Path):

```python
# in tool_shell(), BEFORE shlex.split:
if not os.access("/tmp", os.W_OK):
    tmpdir = os.environ.get("TMPDIR", "/data/data/com.termux/files/usr/tmp")
    cmd = re.sub(r'(?<![/\w])/tmp(?=$|\s|/)', tmpdir, cmd)
    cmd = re.sub(r'(?<![/\w])/tmp/(?=\S)', tmpdir + "/", cmd)
if not os.access("/data", os.R_OK):
    home = os.environ.get("HOME", "/data/data/com.termux/files/home")
    # CRITICAL: negative lookbehind — $HOME starts with /data/, so substring-replace
    # would double-substitute $HOME. Use lookahead/lookbehind to anchor.
    cmd = re.sub(r'(?<![/\w])/data/(?!data/com\.termux)', home + "/", cmd)
    cmd = re.sub(r'(?<![/\w])/data(?![/\w])', home, cmd)
```

**Pitfall:** `cmd.replace("/data", home, 1)` is wrong — `$HOME` is itself `/data/data/com.termux/files/home`, so the first `/data` in the cmd (which is the user's `/data/foo`) gets replaced, but if the cmd already contains `$HOME` expanded (e.g. from smart-fallback), the result is `/data/data/com.termux/files/home/data/data/com.termux/files/home/foo` — the path doubles up. Always use the anchored regex.

Also add `$TMPDIR` to `policy.DEFAULT["write_paths"]` or the path resolves correctly but `policy.is_path_allowed` still denies the write.

## Premature early-stop (sanity check 2 trap)

The shell early-stop heuristic ("stdout non-empty → done") is correct for `wc -l` but **wrong** for `mkdir -p /tmp/x && echo done` followed by a `file_write` that hasn't run yet. Symptom: iter 1 mkdir succeeds with `stdout="mkdir: created directory '/tmp/x'"` — LLM or heuristic declares done, but no file exists. T1 reverse_string task hit this with `status=done` but `file_exists=False`.

**Fix:** add a `wants_artifact_creation` flag to the goal pattern and gate heuristic 2 on it:

```python
wants_file = any(k in goal_lc for k in ("simpan ke", "save to", "tulis ke", "write to", "simpan di", "store in"))
wants_artifact_creation = wants_file or any(k in goal_lc for k in (
    "buat script", "buat file", "create file", "create script", "write file",
    "tulis script", "simpan hasil", "save hasil", "tulis ke file", ".py", ".txt", ".md"
))
# Heuristic 2 only fires when goal doesn't require an artifact AND artifacts are empty
if (not done and nxt in ("continue", "retry")
    and step.get("name") == "shell"
    and obs.get("ok")
    and not wants_file
    and not (wants_artifact_creation and not has_artifact)):
    # ... early-stop only if stdout non-empty
```

## The 6 sanity checks (canonical evaluator pattern)

After this session's debugging, the canonical evaluator has SIX sanity checks, not three. Patch them in order — each is independent:

1. **wants_file + no artifact → override done=False** (BUG-002). Most basic; catches the "LLM said done without checking disk" failure.
2. **shell ok + stdout non-empty + goal doesn't need file → early-stop** (BUG-009). Saves tokens; but gated by `wants_artifact_creation` to avoid premature stops.
3. **shell ok + redirect + file exists on disk → early-stop** (BUG-014). Critical for `echo x > file` tasks where `obs.content=""` but the file was created.
4. **2x fail streak with `not obs.ok` → force replan** (anti-stuck). Without this, the loop burns 5 iters on a command that consistently fails (e.g. `find /data` returns perm denied). After 2 fails, force replan so the LLM tries a different path.
5. **LLM reason admits incompleteness → override done=False** (anti-bohong). When the LLM's own reason contains "belum ada" / "no output" / "tidak ada" / "kosong" but it still returns `done=true`, override to `replan`. Keywords list:

   ```python
   ADMITS_INCOMPLETE = (
       "belum ada", "belum selesai", "tidak ada", "no output", "no artifact",
       "no result", "no data", "not yet", "belum ditampil", "kosong",
       "tidak berhasil", "gagal menampilkan", "tidak ditemukan", "no match"
   )
   if done and any(k in (reason or "").lower() for k in ADMITS_INCOMPLETE):
       done = False; nxt = "replan"
   ```

6. **kind="think" step → never done** (anti-think-only). When the LLM planner emits `kind=think, name=think` and the LLM executor just generates text, the LLM evaluator can hallucinate "done" because the text was relevant. Force `nxt=continue` so the loop proceeds to a real tool step.

**Field-name gotchas (all bit us this session):**
- `step.kind` is set to `"tool"` by executor, but the tool name is in `step.name` (e.g. `"shell"`). Heuristics must check `step.get("name") == "shell"`, not `step.get("kind")`.
- Shell `obs.output` is the stdout, not `obs.content`. The evaluator prompt extraction must include `output` as a fallback, in order: `content_preview → content → output → error → _raw`.
- `is_goal_done()` was originally checking `obs.__done__`, but `__done__` is set on the action dict, not on obs. Scan `task["history"][i]["action"]` instead, and accept both `__done__=True` and `stop=True with "early-stop" in reason`.

## Re-runnable script

The full working script is in `~/agent/eval/eval_v2.py`. Key structure:

```python
TASKS = [
    ("T1", "Buat script Python reverse_string di /tmp/agent_test/reverse.py ..."),
    ("T2", "Buat file hello.py di /tmp/agent_test/ ..."),
    ("T3", "Cari 5 file .log terbesar di /data ..."),
    ("T4", "Cek log Hermes agent untuk error 500 dalam 1 jam terakhir"),
    ("T5", "Hitung jumlah baris di ~/agent/README.md"),
    ("T6", "Simpan ke /tmp/agent_test/notes.txt: meeting Senin jam 10"),  # redirect case
    ("T7", "Cari semua file .txt di /tmp"),
    ("T8", "Analisis log ~/agent/logs/20260903-202111-32037f.log"),
]

for tid, goal in TASKS:
    task = memory.new(goal, budget_tokens=50_000, budget_iters=5, timeout=180, model="Free-Kombo")
    rep = reporter.Reporter(task)
    loop.run(task, rep)  # BUG-008: must pass Reporter

    # ground truth check (Termux-aware)
    ok, detail = check_ground_truth(tid, task, _resolve_path)
    results.append({"tid": tid, "status": task["status"], "ground_truth": ok, "detail": detail, "iters": len(task["history"]), "elapsed_s": elapsed})
```

## v0.5 → v0.6 patch results

| Metric | v0.5 (pre-fix) | v0.5 (post-fix) |
|--------|----------------|-----------------|
| Status done | 0/8 (0%) | 8/8 (100%) |
| GT pass | 0/8 (0%) | 7/8 (87.5%) |
| Avg iters | 4.4 | 2.0 |
| Common failure | stuck in retry loop | none (T4 partial) |

The remaining T4 failure is a **planner problem** (LLM doesn't know where Hermes keeps its log) — fixable via goal decomposition interview or path injection, not via the evaluator.

## Task design rules

1. **Mix the type distribution** — at least one of each:
   - `file_write` (e.g. "buat hello.py di /tmp/agent_test/")
   - `code` skill (e.g. "generate reverse_string function")
   - `shell` with stdout output (e.g. "cari 5 file .log terbesar")
   - `shell` with redirect (e.g. "simpan ke /tmp/x.txt: ...")
   - `read`/`analyze` (e.g. "hitung jumlah baris README.md")
   - 1-2 tasks that **should fail** (control: e.g. "kirim email ke admin@x.com" — no email tool) — these test that the agent stops cleanly instead of spinning

2. **Per-task ground truth checker** — never trust `task["status"] == "done"` alone. The LLM can lie. The checker inspects disk **using the same path resolver the agent uses**:

   ```python
   from core.executor import _resolve_path

   if tid == "T1":
       for p in [Path("/tmp/agent_test/reverse.py"),
                 Path(_resolve_path("/tmp/agent_test/reverse.py"))]:
           if p.exists() and "def reverse" in p.read_text():
               ok = True; break
   elif tid == "T2":
       # shell stdout case: cek obs.content_preview (priority) → content → output
       last = task["history"][-1]["obs"] if task["history"] else {}
       out = (last.get("content_preview") or last.get("content") or last.get("output") or "")
       ok = len(out.strip()) > 10
   elif tid == "T3":
       # shell redirect case: cek file exists on Termux path
       p = Path(_resolve_path("/tmp/agent_test/notes.txt"))
       ok = p.exists() and "meeting" in p.read_text()
   ```

3. **Report three numbers, not one** — `done + GT` (both true, agent is honest AND correct), `done only` (agent said done but ground truth failed), `GT only` (ground truth passed but agent didn't declare done). The deltas are diagnostic:
   - `done only` high → LLM evaluator lying (pitfall #2)
   - `GT only` high → LLM evaluator too conservative OR heuristic not aggressive enough (pitfalls #13, #14)
   - both low → planner or executor broken
   - **`done only` high with files actually present in $TMPDIR but not /tmp** → GT checker missing path resolution (this session's T1/T2/T6 false-negatives)

4. **Clean the env between tasks** — `rm -rf $TMPDIR/agent_test; mkdir -p $TMPDIR/agent_test` before each task. Otherwise the previous run's artifacts can fool the ground truth checker. Use `$TMPDIR`, not `/tmp`, in the cleanup script.

5. **Per-task budget** — set `budget_iters=5`, `budget_tokens=50_000`, `timeout=180` for v0.5. Tune up for harder tasks; tune down to expose infinite loops faster.

## Interpreting results

| Pattern | Root cause | Fix |
|---------|-----------|-----|
| 0/8, all `budget_exhausted`, logs full of `eval 🔁 retry` | pitfall #13 (LLM returns retry even on success) | add `_rule_fallback` anti-loop with 3-retry limit |
| 0/8, redirect tasks fail (T6 specifically) | pitfall #14 (shell redirect → `obs.content=""`) | detect `>` target in executor, check file exists in evaluator sanity check 3 |
| `done only` = 5, `GT only` = 0 | pitfall #2 (LLM says done without checking disk) | override `done=False` if `wants_file` and `artifacts` empty |
| `GT only` = 5, `done only` = 0 | pitfall #13 + heuristic not firing | move sanity check 2 BEFORE `nxt=retry` branch, not after; also check `obs.output` not just `obs.content` |
| All `crashed` with `TypeError: run() missing 1 required positional argument: 'rep'` | BUG-008 | construct `Reporter(task)` first |
| `done only` high but file IS on disk at `$TMPDIR/...` not `/tmp/...` | **GT checker missing Termux path resolution** | apply `_resolve_path()` in checker too |
| `done only` high after `mkdir` step but no file written | **premature early-stop** (heuristic 2 fired on mkdir stdout) | gate heuristic 2 with `wants_artifact_creation` flag |
| `done` with reason containing "belum ada" / "no output" | LLM evaluator lying (sanity 5 missing) | add reason-keyword check (ADMITS_INCOMPLETE) |
| `done` after `kind=think` step with no tool call | anti-think-only missing (sanity 6) | force `nxt=continue` for think steps |
| `/data` paths cause perm denied or `find /data` fails | Termux sandbox restriction | auto-substitute `/data` → `$HOME` in tool_shell + planner smart-fallback |
| `find -printf` returns nothing in smart-fallback output | toybox `find` lacks `-printf` | chain `find -printf` → `ls -la \| sort` in the fallback cmd |

## After every patch, re-run

```bash
cd ~/agent && python eval/eval_v2.py 2>&1 | grep -E "^[✅⚠️❌=]"
```

If success rate doesn't go up, the patch missed the actual failure mode. Don't trust "I think this fixed it" — re-run.

## Cost note

8 tasks × ~50k tokens × Free-Kombo = ~400k tokens. On the free provider, that's 8-15 minutes wall time depending on rate limits. Run during off-peak hours or after rotating to a less-loaded model in the combo.

## What this benchmark does NOT measure

- **Latency per step** — that's `tail -f logs/<task_id>.log` territory, not eval.
- **Token efficiency** — add a `tokens` column and `sum(r["tokens"] for r in results) / total` to get tokens-per-task. v0.5 averages ~6k tokens per simple task.
- **Skill quality in isolation** — call each skill directly from a test script, not through the loop. The loop adds LLM-eval noise.
- **Real-world goal ambiguity** — the benchmark uses literal goals. Real users say "fix that thing from yesterday". That's a planner problem, not an executor problem; test it separately.
- **Agent honesty under multi-step partial success** — covered partially by the `wants_artifact_creation` guard, but a real test would be a 3-step goal where step 1 succeeds with empty stdout and steps 2-3 must execute. Add a "plan-then-write-then-verify" task to expose premature-stops.
