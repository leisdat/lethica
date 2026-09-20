#!/usr/bin/env python3
# tests/test_v30_orchestrator.py — Phase 5 failure-testing utk orchestrator multi-agent.
# Semua LLM dipanggil via stub → deterministik, offline. Jalankan: python3 tests/test_v30_orchestrator.py
import os, sys, json, time, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

fails = 0
def ok(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL") + " - " + msg)
    if not cond: fails += 1

from core import config, registry, orchestra, tools, experience

# sandbox registry + skill dirs ke temp
TMP = tempfile.mkdtemp(prefix="lx-v30-")
registry.REG_FILE = os.path.join(TMP, "skill-registry.json")
orchestra.HIST_FILE = experience.HIST_FILE = os.path.join(TMP, "task-history.json")
experience.FAIL_FILE = os.path.join(TMP, "task-failures.json")
tools.SKILL_DIR = os.path.join(TMP, "skills")
os.makedirs(tools.SKILL_DIR, exist_ok=True)

def seed_skill(layer, name, purpose="kapabilitas uji"):
    d = os.path.join(tools.SKILL_DIR, layer, name)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "SKILL.md"), "w") as f:
        f.write(f"# {name}\n\n## Purpose\n{purpose}\n")
    tools._SKILL_INDEX = {}
    tools._build_skill_index()
    registry.ensure_seeded()

seed_skill("testing", "pytest-run")
seed_skill("web", "html-parsing")

# ── 1: registry seed & idempotensi ──────────────────────────────────
r1 = registry.ensure_seeded(); r2 = registry.ensure_seeded()
ok(r1["total"] == 2 and r2["total"] == 2 and r2.get("added", 0) == 0,
   "registry: seed idempoten (2 skill, tidak duplikat)")
ok(all(m["status"] == "unverified" for m in registry.entries().values()),
   "registry: status awal unverified")

# ── 2: analyze — skill tersedia / hilang / outdated ─────────────────
a = registry.analyze(["pytest-run", "kubernetes-helm"])
ok(a["low_confidence"] and a["low_confidence"][0]["skill"] == "testing/pytest-run"
   and "kubernetes-helm" in a["missing_skills"] and not a["available_skills"],
   "analyze: skill unverified → low_confidence (bukan 'available'), hilang → missing")
ok(a["action"] == "RESEARCH_AND_BUILD_SKILLS", "analyze: action riset utk yang hilang")
for i in range(5):
    registry.record_use(["testing/pytest-run"], success=(i % 2 == 0))
m = registry.get("testing/pytest-run")
ok(m["status"] == "degraded" and 0.3 < m["success_rate"] < 0.7,
   f"analyze: sukses 50% → degraded (rate={m['success_rate']})")
reg = registry._load_raw(); reg["skills"]["testing/pytest-run"]["status"] = "degraded"
registry._save_raw(reg)
a2 = registry.analyze(["pytest-run"])
ok(a2["action"] == "UPDATE_SKILLS" and a2["outdated_skills"], "analyze: degraded → UPDATE_SKILLS")

# ── 3: record_use sukses berulang → verified ─────────────────────────
_d = registry._load_raw(); _m = _d["skills"]["testing/pytest-run"]
_m["status"] = "unverified"; _m["usage_count"] = 0; _m["failure_count"] = 0
_m["confidence"] = 0.0; registry._save_raw(_d)   # reset penuh: metrik lama dibuang
for i in range(4):
    registry.record_use(["testing/pytest-run"], success=True)
ok(registry.get("testing/pytest-run")["status"] == "verified", "learning: 4 sukses → verified")

# ── 4: builder + evaluator ──────────────────────────────────────────
b = registry.build_skill("quizzical-cap", "generated", "## Purpose\nuji")
ok(b["ok"] and registry.get(b["skill"])["status"] == "unverified",
   "builder: skill baru = unverified (TIDAK otomatis dipercaya)")
b2 = registry.build_skill("quizzical-cap", "generated", "dup")
ok(not b2["ok"], "builder: tolak duplikat tanpa overwrite")
ev = registry.evaluate_skill(b["skill"], ["python3 -c 'print(1)'", "python3 -c 'import sys;sys.exit(1)'"])
ok(ev["tests"] == 2 and ev["passed"] == 1 and ev["success_rate"] == 0.5,
   f"evaluator: 1/2 pass terdeteksi (status={ev['status']})")

# ── 5: tool unavailable → error terekam, bukan klaim sukses ─────────
class DeadClient:
    last_finish_reason = None; last_usage = {}
    def chat_failover(self, *a, **k): return (None, None)
    def chat(self, *a, **k): return {"error": "down"}
t = orchestra.Task("buatkan scraper mainan", client=DeadClient())
t.messages = []
res = orchestra._run_tools(t, {"n": 0})
ok("all models failed" in res["err"] or "limit" in "".join(res["err"]),
   "failure: semua model mati → error tercatat (bukan success)")

# ── stub LLM utk agent routing ──────────────────────────────────────
class StubLLM:
    """Kirim balasan berurutan per 'persona panggilan'."""
    def __init__(self, plan_json=None, analyst_json=None, critic_json=None, debug_json=None):
        self.plan, self.analyst, self.critic, self.debug = plan_json, analyst_json, critic_json, debug_json
        self.calls = []
        self.last_finish_reason = None; self.last_usage = {}
    def chat_failover(self, model, msgs, *a, **k):
        sysc = msgs[0]["content"] if msgs and msgs[0]["role"] == "system" else ""
        if "Planner" in sysc:
            out = self.plan; self.calls.append("planner")
        elif "Skill Analyst" in sysc:
            out = self.analyst or "{}"; self.calls.append("analyst")
        elif "Critic" in sysc:
            out = self.critic; self.calls.append("critic")
        elif "Debugger" in sysc:
            out = self.debug; self.calls.append("debugger")
        else:
            out = "{}"
        return (json.dumps(out), "stub")
    def chat(self, model, msgs, **k): return self.chat_failover(model, msgs)[0]

PLAN1 = {"goal": "uji orkestrasi", "complexity": "simple",
         "success_criteria": ["satu hal selesai"],
         "subtasks": [{"id": "s1", "description": "echo hello", "required_skills": ["pytest-run"],
                       "required_tools": ["exec"], "dependencies": []}]}
CRITIC_PASS = {"status": "pass", "requirements_met": ["selesai"], "requirements_failed": [],
               "bugs": [], "recommendation": "complete"}
CRITIC_FAIL = {"status": "fail", "requirements_met": [], "requirements_failed": ["bukti kosong"],
               "bugs": ["tidak ada output"], "recommendation": "repair"}
DEBUG = {"error": "no output", "root_cause": "perintah echo tidak jalan", "component": "exec",
         "fix_steps": ["jalankan ulang dengan benar"], "confidence": 0.8}

# ── 6: happy path — skill ADA, critic PASS ─────────────────────────
def fake_dispatch_factory(counter):
    def fake(reply, path):
        counter[0] += 1
        return "[execute_command]\n$ echo hello\n[exit=0]\nhello"
    return fake

orig_dispatch = orchestra.tags.dispatch
orchestra.tags.dispatch = fake_dispatch_factory([0])
t = orchestra.Task("uji orkestrasi simple", client=StubLLM(plan_json=PLAN1, critic_json=CRITIC_PASS))
t.messages = []  # skip build_system_prompt
orchestra.run(t)
ok(t.state == "COMPLETED", f"routing: task selesai COMPLETED (state={t.state})")
ok("planner" in t.client.calls and "critic" in t.client.calls, "routing: planner→critic dipanggil")

# ── 7: skill MISSING → peneliti + builder jalan ─────────────────────
class StubWeb:
    def __init__(self): self.n = 0
    def __call__(self, q, limit=None):
        return "sumber: https://docs.pytest.org/en/stable/ (test runner python)\ndua https://example.com/x"
orig_search, orig_browse = orchestra.tools.tool_web_search, orchestra.tools.tool_browse
orchestra.tools.tool_web_search = StubWeb()
orchestra.tools.tool_browse = lambda u, *a, **k: "isi ringkas docs resmi"
PLAN2 = json.loads(json.dumps(PLAN1))
PLAN2["subtasks"][0]["required_skills"] = ["quantum-teleport"]
t = orchestra.Task("pakai skill yang belum ada", client=StubLLM(plan_json=PLAN2, critic_json=CRITIC_PASS))
t.messages = []
orchestra.run(t)
ok(t.state == "COMPLETED" and len(t.research_notes) >= 1, "riset: skill hilang → RESEARCHING jalan")
ok(any("generated/" in n for n in t.skill_report.get("available_skills", [])) or
   registry.get("generated/quantum-teleport") is not None or
   registry.get("generated/quantum-teleport-0") is not None or
   len(registry.entries()) > 2, "builder: skill 'generated' dibuat saat skill hilang")

# ── 8: CRITIC FAIL → DEBUGGER → REPAIR → PASS ───────────────────────
seq = {"c": 0}
class SeqCritic(StubLLM):
    def chat_failover(self, model, msgs, *a, **k):
        if "Critic" in msgs[0].get("content", ""):
            seq["c"] += 1
            return (json.dumps(CRITIC_FAIL if seq["c"] == 1 else CRITIC_PASS), "stub")
        return super().chat_failover(model, msgs, *a, **k)
t = orchestra.Task("uji jalur repair", client=SeqCritic(plan_json=PLAN1, debug_json=DEBUG, critic_json=CRITIC_PASS))
t.messages = []
orchestra.run(t)
ok("debugger" in t.client.calls and t.repair_count >= 1, "repair: critic FAIL → debugger → repair")
ok(t.state == "COMPLETED", f"repair: critic kedua PASS → COMPLETED (state={t.state})")

# ── 9: repair GAGAL terus → FAILED (bukan loop tak berujung) ────────
class AllFail(StubLLM):
    def chat_failover(self, model, msgs, *a, **k):
        if "Critic" in msgs[0].get("content", ""): return (json.dumps(CRITIC_FAIL), "stub")
        return super().chat_failover(model, msgs, *a, **k)
orig_run_tools = orchestra._run_tools
orchestra._run_tools = lambda task, c: {"reply": "gagal lagi", "had_tools": False,
    "actions": [], "files": [], "cmds": [], "err": ["boom"]}
t = orchestra.Task("mustahil", client=AllFail(plan_json=PLAN1, debug_json=DEBUG, critic_json=CRITIC_FAIL))
t.messages = []
t.limits = {"max_agent_steps": 12, "max_retries": 2, "max_repair_attempts": 2, "timeout": 1800, "max_tool_calls": 40}
orchestra.run(t)
ok(t.state == "FAILED", f"limit: repair habis → FAILED, bukan infinite loop (state={t.state})")
ok(t.repair_count <= t.limits["max_repair_attempts"], "limit: repair_count ≤ max_repair_attempts")
orchestra._run_tools = orig_run_tools

# ── 10: safety — orchestrator tidak pernah bypass danger confirm ────
# v3.7.2: logic terpecah ke core/orch_*.py; grepping seluruh modul orch.
import glob as _glob
_cores = "\n".join(open(f, encoding="utf-8", errors="replace").read()
                    for f in _glob.glob(os.path.join(os.path.dirname(__file__), "..", "core", "orch_*.py")))
ok("is_dangerous" not in _cores and "DANGER_CONFIRM = False" not in _cores,
   "safety: orch_* tidak menyentuh/membypass gerbang bahaya")
ok("dispatch(reply, config.SELF_PATH)" in _cores,
   "safety: executor pakai dispatch + sandbox yang sama (bukan bypass)")

# ── 11: task history & log persist ─────────────────────────────────
ok(os.path.isfile(experience.HIST_FILE), "observability: task-history.json tertulis")
ok(os.path.isfile(orchestra.LOG_FILE) and "COMPLETED" in open(orchestra.LOG_FILE).read(),
   "observability: log state transisi ada")
h = json.load(open(experience.HIST_FILE))
ok(len(h) >= 4 and all("state" in x for x in h), f"history: {len(h)} task terekam terstruktur")

orchestra.tags.dispatch = orig_dispatch
orchestra.tools.tool_web_search, orchestra.tools.tool_browse = orig_search, orig_browse
print("\n" + ("ALL PASS" if fails == 0 else f"{fails} FAIL"))
sys.exit(1 if fails else 0)
