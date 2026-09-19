#!/usr/bin/env python3
# tests/test_v32_parallel.py — deterministik, tanpa LLM live (fake executor/sleep).
# Jalankan: python3 tests/test_v32_parallel.py
import os, sys, json, time, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
fails = 0
def ok(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL") + " - " + msg)
    if not cond: fails += 1

from core import config, registry, orchestra, tools, experience

TMP = tempfile.mkdtemp(prefix="lx-v32-")
experience.HIST_FILE = os.path.join(TMP, "task-history.json")
experience.FAIL_FILE = os.path.join(TMP, "task-failures.json")
registry.REG_FILE = os.path.join(TMP, "skill-registry.json")
tools.SKILL_DIR = os.path.join(TMP, "skills"); os.makedirs(tools.SKILL_DIR)
tools._SKILL_INDEX = {}

class StubLLM:
    last_finish_reason = None; last_usage = {}
    def __init__(self, responses): self.responses = responses
    def chat_failover(self, model, msgs, *a, **k):
        s = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
        key = ("Planner" if "Planner" in s else "Critic" if "Critic" in s
               else "Debugger" if "Debugger" in s else "other")
        self.last_sys = s
        return (json.dumps(self.responses.get(key, "{}")), "stub")
    def chat(self, *a, **k): return {"error": "x"}

def task_with(plan, critic=None, maxc=3, limits=None):
    CRIT = critic or {"status": "pass", "requirements_met": ["ok"],
                      "requirements_failed": [], "bugs": [], "recommendation": "complete"}
    t = orchestra.Task("uji paralel", client=StubLLM({"Planner": plan, "Critic": CRIT}))
    t.messages = []
    t.limits = dict(t.limits)
    t.limits["max_concurrent_agents"] = maxc
    if limits: t.limits.update(limits)
    return t

PASS = {"actions": [], "files_changed": [], "commands_executed": [],
        "errors": [], "tests": [], "reply_tail": "ok"}
def okres(files=None): return {**PASS, "status": "success", "files_changed": files or []}
def failres(err="boom"): return {**PASS, "status": "failed", "errors": [err]}

orig_exec = orchestra.executor
def stub_exec(fn):
    orchestra.executor = fn
def restore(): orchestra.executor = orig_exec

# ── 1: DAG independent nodes → paralel ───────────────────────────────
concurrency_seen = [0]
def slow_ok(task, st):
    with task.lock:
        concurrency_seen[0] = max(concurrency_seen[0], sum(
            1 for s in task.sub_states.values() if s == "RUNNING"))
    time.sleep(0.15)
    return okres()
stub_exec(slow_ok)
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [{"id": "A", "description": "riset docs", "depends_on": []},
                            {"id": "B", "description": "riset contoh", "depends_on": []},
                            {"id": "C", "description": "riset error", "depends_on": []}]})
t0 = time.time(); orchestra.run(t); dur = time.time() - t0
restore()
ok(t.state == "COMPLETED" and all(t.sub_states[i] == "COMPLETED" for i in "ABC"),
   "1 independent nodes semua COMPLETED")
ok(concurrency_seen[0] >= 2 and dur < 0.45,
   f"1 BUKTI paralel: conc_seen={concurrency_seen[0]} dur={dur:.2f}s < serial 0.45s")
ok(t.parallel_stats["max_concurrency"] >= 2 and t.parallel_stats["parallel"],
   f"1 stats paralel: max_conc={t.parallel_stats['max_concurrency']}")

# ── 2: sequential deps tetap urut ─────────────────────────────────────
order = []
def spy(task, st):
    order.append(st["id"]); time.sleep(0.02)
    return okres()
stub_exec(spy)
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [{"id": "A", "description": "db", "depends_on": []},
                            {"id": "B", "description": "api", "depends_on": ["A"]},
                            {"id": "C", "description": "ui", "depends_on": ["B"]}]})
orchestra.run(t); restore()
ok(order == ["A", "B", "C"] and t.state == "COMPLETED", f"2 sequential terurut: {order}")
ok(t.parallel_stats["max_concurrency"] <= 1, "2 sequential tanpa paralel palsu")

# ── 3: concurrency limit dihormati ───────────────────────────────────
peak = [0]; lock3 = threading.Lock()
def count(task, st):
    with lock3:
        peak[0] = max(peak[0], sum(1 for s in task.sub_states.values() if s == "RUNNING"))
    time.sleep(0.1)
    return okres()
stub_exec(count)
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [{"id": c, "description": "riset x", "depends_on": []}
                            for c in "ABCDEF"]}, maxc=2)
orchestra.run(t); restore()
ok(peak[0] <= 2, f"3 max RUNNING bersamaan ≤ maxc=2 (peak={peak[0]})")
ok(all(v == "COMPLETED" for v in t.sub_states.values()) and len(t.sub_states) == 6,
   "3 semua 6 node COMPLETED dalam limit")

# ── 4: ready queue ───────────────────────────────────────────────────
plan4 = {"goal": "g", "complexity": "simple", "success_criteria": [],
         "subtasks": [{"id": "A", "description": "a", "depends_on": []},
                      {"id": "B", "description": "b", "depends_on": ["A"]},
                      {"id": "C", "description": "c", "depends_on": []}]}
t4 = task_with(plan4); t4.plan = t4.plan or {}
# unit-test ready_nodes murni:
import core.orchestra as O
g = O.graph_validate(plan4["subtasks"])
t4.plan = {"goal": "g", "subtasks": plan4["subtasks"], "success_criteria": []}
t4.graph = g
for sid in g["order"]: t4.sub_states[sid] = "PENDING"
sch = O.Scheduler(t4)
r0 = {s["id"] for s in sch.ready_nodes()}
ok(r0 == {"A", "C"}, f"4 ready awal = node tanpa dep: {r0}")
t4.sub_states["A"] = "COMPLETED"
r1 = {s["id"] for s in sch.ready_nodes()}
ok("B" in r1, "4 B READY setelah A COMPLETED")

# ── 5/6/7/8: blocked, failed branch, partial failure, isolation ──────
def a_fail(task, st):
    time.sleep(0.02)
    return failres() if st["id"] == "C" else okres()
stub_exec(a_fail)
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [{"id": "A", "description": "a", "depends_on": []},
                            {"id": "B", "description": "b", "depends_on": []},
                            {"id": "C", "description": "c", "depends_on": []},
                            {"id": "D", "description": "d", "depends_on": ["A", "B", "C"]}]})
orchestra.run(t); restore()
ok(t.sub_states["A"] == "COMPLETED" and t.sub_states["B"] == "COMPLETED",
   "7/8 partial failure: branch A,B TETEP valid (isolated)")
ok(t.sub_states["C"] == "FAILED" and t.sub_states["D"] == "BLOCKED",
   f"5/6/8 C FAILED → D BLOCKED (bukan jalankan buta): {t.sub_states['D']}")
ok(t.merged and any("D" in w for w in t.merged["warnings"]),
   "10 merger mencatat warning tanpa klaim sukses")
ok(any(w["id"] == "D" and w["status"] == "failed" for w in t.merged["subtasks"]),
   "10 merger: D status failed (bukti dari result, bukan asumsi)")

# ── 9/10/11: conflict detection ──────────────────────────────────────
sa = {"id": "A", "description": "buat file app.py", "type": "WRITE", "depends_on": []}
sb = {"id": "B", "description": "edit file app.py", "type": "WRITE", "depends_on": []}
sc = {"id": "C", "description": "buat file api.py", "type": "WRITE", "depends_on": []}
sd = {"id": "D", "description": "baca docs", "type": "READ_ONLY", "depends_on": []}
ok(not orchestra.safe_parallel(sa, sb, orchestra.predict_writes(sa), orchestra.predict_writes(sb)),
   "10 same-file WRITE×WRITE → SERIAL (conflict terdeteksi)")
ok(orchestra.safe_parallel(sa, sc, orchestra.predict_writes(sa), orchestra.predict_writes(sc)),
   "9 write file berbeda (disjoint terbukti) → paralel allowed")
ok(orchestra.safe_parallel(sd, sd, set(), set()), "11 READ×READ paralel")
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [dict(sa), dict(sb)]})
calls = []
def track(task, st):
    with task.lock:
        calls.append((st["id"], task.sub_states.get("A"), task.sub_states.get("B")))
    return okres()
stub_exec(track)
orchestra.run(t); restore()
par = any(a and b for _, a, b in calls if a == "RUNNING" and b == "RUNNING")
ok(not par and t.parallel_stats["conflicts"] >= 1,
   "10 eksekusi nyata: dua writer file SAMA tidak pernah RUNNING bareng (serialized)")

# ── 12: cancellation (budget timeout) ────────────────────────────────
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [{"id": "A", "description": "a", "depends_on": []}]},
              limits={"timeout": 0})   # timeout langsung → cancel_all
stub_exec(lambda task, st: okres())
orchestra.run(t); restore()
ok("RESOURCE_LIMIT" in (t.error or ""), f"12 budget habis → reason eksplisit: {t.error}")

# ── 13: resource limit max_total_agent_calls ─────────────────────────
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [{"id": c, "description": "riset x", "depends_on": []} for c in "ABC"]},
              maxc=3, limits={"max_total_agent_calls": 2})
t.agent_calls = 2  # seed: sudah 2
stub_exec(lambda task, st: okres())
orchestra.run(t); restore()
ok("RESOURCE_LIMIT" in (t.error or "") and any(v == "CANCELLED" for v in t.sub_states.values()),
   "13 MAX_TOTAL_AGENT_CALLS → RESOURCE_LIMIT_REACHED + node CANCELLED (terlihat, bukan diam)")

# ── 14: capability matching ──────────────────────────────────────────
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": []})
m = orchestra.match_capability(t, {"id": "x", "description": "riset dokumentasi",
                                   "required_skills": ["web/docs"], "type": "READ_ONLY"})
ok(m["agent"] in ("researcher", "browser", "coder") and "skills" in m,
   f"14 agent dipilih by tipe/skill: {m['agent']}")
st_w = orchestra.classify_subtask({"description": "buat file main.py dan edit config", "required_tools": []})
st_t = orchestra.classify_subtask({"description": "jalankan pytest test_main.py", "required_tools": []})
st_r = orchestra.classify_subtask({"description": "baca dokumentasi resmi", "required_tools": []})
ok(st_w == "WRITE" and st_t == "TEST" and st_r == "READ_ONLY",
   f"9 klasifikasi: {st_w}/{st_t}/{st_r}")

# ── 15: merger tidak klaim sukses ────────────────────────────────────
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [{"id": "A", "description": "a", "depends_on": []}]})
stub_exec(lambda task, st: okres(["f.py"]))
orchestra.run(t); restore()
mg = t.merged
ok("status" not in mg or mg.get("status") in (None,),
   "15 merger tidak punya field klaim sukses (hanya Critic yang memutuskan)")
ok(mg["artifacts"] == ["f.py"] and mg["task_id"] == t.id, "15 merger berisi artifacts+task_id")

# ── 16/18: memory persistence paralel stats (FEATURE 16) ─────────────
h = experience.all_tasks()
last = h[-1]
ok(last.get("parallel_stats", {}).get("parallel") in (True, False)
   and "parallel_stats" in last,
   f"16 task memory menyimpan parallel_stats: {last.get('parallel_stats')}")

# ── 17: parallel repair (dua branch gagal non-conflict → repair paralel;
#        conflict → serialize) ────────────────────────────────────────
repair_seq = []
def fail_then_pass(task, st):
    key = st["id"]
    n = sum(1 for x in repair_seq if x[0] == key)
    repair_seq.append((key, threading.current_thread().name))
    return failres("x") if n == 0 else okres()
stub_exec(fail_then_pass)
CRIT_FAIL = {"status": "fail", "requirements_met": [], "requirements_failed": ["coba lagi"],
             "bugs": [], "recommendation": "retry"}
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [{"id": "A", "description": "riset alpha", "depends_on": []},
                            {"id": "B", "description": "riset beta", "depends_on": []}]},
              critic=CRIT_FAIL, maxc=2)
# critic fail sekali lalu pass
t.client = StubLLM({"Planner": t.plan, "Critic": CRIT_FAIL})
class CriticSeq(StubLLM):
    n = 0
    def chat_failover(self, model, msgs, *a, **k):
        s = msgs[0]["content"] if msgs[0]["role"] == "system" else ""
        if "Critic" in s:
            self.n += 1
            r = CRIT_FAIL if self.n <= 1 else {"status": "pass", "requirements_met": ["ok"],
                "requirements_failed": [], "bugs": [], "recommendation": "complete"}
            return (json.dumps(r), "stub")
        return super().chat_failover(model, msgs, *a, **k)
t.client = CriticSeq({"Planner": t.plan})
orchestra.run(t); restore()
ok(t.state == "COMPLETED" and all(v == "COMPLETED" for v in t.sub_states.values()),
   f"17 retry paralel: dua branch gagal→repair→COMPLETED semua: {t.sub_states}")

# ── 19: regression v3.1 — serial tetap saat maxc=1 ───────────────────
t = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
               "subtasks": [{"id": "A", "description": "a", "depends_on": []},
                            {"id": "B", "description": "b", "depends_on": []}]}, maxc=1)
seq = []
stub_exec(lambda task, st: (seq.append(st["id"]), okres())[1])
orchestra.run(t); restore()
ok(seq == ["A", "B"] and t.parallel_stats["max_concurrency"] == 0,
   "19 maxc=1 → jalur serial v3.1.2 utuh (urutan graph)")

# ── 20: tidak ada orphan RUNNING ─────────────────────────────────────
ok(not any(v == "RUNNING" for v in t.sub_states.values()), "20 tidak ada state RUNNING yatim")

# ── 21: _scan_cmd_files — file yang DISEBUT bukan artefak ────────────
import os as _os, shutil as _sh
_d = _os.path.join(config.WORKSPACE, "_v32probe")
_os.makedirs(_d, exist_ok=True)
for _n in ("written.txt", "mention.txt"):
    open(_os.path.join(_d, _n), "w").write("x")
def _scan(c):
    f = []; orchestra._scan_cmd_files(c, f); return f
_a = _scan("ls -la %s && find . -name mention.txt" % _d)
_b = _scan("cd %s && cat > written.txt << 'EOF'\nx\nEOF" % _d)
_sh.rmtree(_d)
ok(not _a, f"21a file yang hanya disebut (find/ls) TIDAK jadi artefak: {_a}")
ok(any("written.txt" in x for x in _b), f"21b redirect/heredoc tetap jadi artefak: {_b}")

# ── 22: derive status — tanpa marker STATUS, tool jalan & tanpa error = success ─
class _NoStatus(StubLLM):
    """Model lemah: memanggil tool tapi lupa menulis STATUS: success."""
    def __init__(self): self.responses = {}
    def chat_failover(self, model, msgs, *a, **k):
        return (json.dumps({"reply": "sudah selesai, tidak ada error.",
                            "tool_calls": [{"name": "write_file", "parameters": {
                                "path": os.path.join(TMP, "x.txt"), "content": "y"}}]}), "stub")

_t2 = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
                 "subtasks": [{"id": "A", "description": "a", "depends_on": []}]})
_t2.client = _NoStatus()
_t2.plan = {"goal": "g", "complexity": "simple", "success_criteria": [],
            "subtasks": [{"id": "A", "description": "a", "depends_on": []}]}
_st = {"id": "A", "description": "a", "required_skills": [], "required_tools": [],
       "depends_on": [], "type": "WRITE", "agent": "coder", "skills": [],
       "health": None, "score": 0.0}
_res = orchestra.run_subtask(_t2, _st, _t2.client, {"n": 0})
ok(_res["status"] == "success",
   f"22 tanpa marker STATUS: tool jalan & tanpa error → success (bukan partial): "
   f"{_res['status']}")

# ── 23: worker melempar → node FAILED terisolasi, bukan RUNNING yatim ──
class _Boom:
    def __call__(self, task, st): raise RuntimeError("reply=None boom")
_t3 = task_with({"goal": "g", "complexity": "simple", "success_criteria": [],
                 "subtasks": [{"id": "A", "description": "a", "depends_on": []},
                              {"id": "B", "description": "b", "depends_on": []}]}, maxc=1)
stub_exec(_Boom())
try:
    orchestra.run(_t3)
except Exception as e:
    pass
restore()
ok(all(v != "RUNNING" for v in _t3.sub_states.values()),
   f"23 worker melempar exception → tidak ada node nyangkut RUNNING: {_t3.sub_states}")
ok(_t3.sub_states.get("A") in ("FAILED", "BLOCKED", "CANCELLED"),
   f"23b node error ditandai terminal-state: {_t3.sub_states}")

# ── 24: scope guard — agent dilarang menyentuh project lain ──────────
import core.config as _cfg
_td = os.path.join(config.WORKSPACE, "v32_live")
_prev = getattr(_cfg, "TASK_DIR", None)
_cfg.TASK_DIR = _td
try:
    _g = [
        ("cd ~/lethica/workspace/atria/auto_reg && rm -f diag.log", True),
        ("cd ~/lethica/workspace/atria/auto_reg && ls -la", True),
        ("cd ~/lethica/workspace/v32_live && python3 test_calc.py", False),
        ("nohup python3 mock_server.py --port 8970", False),
    ]
    _bad = [c for c, want in _g if bool(tools._scope_violation(c)) != want]
finally:
    _cfg.TASK_DIR = _prev
ok(not _bad, f"24 scope guard: cd/rm ke luar task-dir diblok, dalam task-dir aman: {_bad}")

print("\n" + ("ALL PASS" if fails == 0 else f"{fails} FAIL"))
sys.exit(1 if fails else 0)
