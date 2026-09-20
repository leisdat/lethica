#!/usr/bin/env python3
# tests/test_v31_experience.py — deterministic suite v3.1 (LLM via stub).
# Fitur 1-14 + regresi. Jalankan: python3 tests/test_v31_experience.py
import os, sys, json, time, tempfile, glob as _glob
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
fails = 0
def ok(cond, msg):
    global fails
    print(("PASS" if cond else "FAIL") + " - " + msg)
    if not cond: fails += 1

from core import config, registry, orchestra, tools, experience

TMP = tempfile.mkdtemp(prefix="lx-v31-")
experience.HIST_FILE = os.path.join(TMP, "task-history.json")
experience.FAIL_FILE = os.path.join(TMP, "task-failures.json")
registry.REG_FILE = os.path.join(TMP, "skill-registry.json")
orchestra.HIST_FILE = experience.HIST_FILE
tools.SKILL_DIR = os.path.join(TMP, "skills"); os.makedirs(tools.SKILL_DIR)

# ── 1: task memory persistence ──────────────────────────────────────
t = orchestra.Task("Buat scraper produk dengan playwright di web A", client=None)
t.state = "COMPLETED"; t.plan = {"goal": "g", "subtasks": [{"id": "s1", "description": "x"}]}
t.subtask_results = {"s1": {"status": "success", "actions": ["write_file: x.py"],
                            "files_changed": ["scraper.py"], "errors": [],
                            "commands_executed": [], "tests": []}}
t.critic = {"status": "pass", "requirements_met": ["scraper jadi"]}
t.skill_report = {"available_skills": ["web/scraping"], "missing_skills": [],
                  "outdated_skills": [], "low_confidence": [], "required_skills": []}
t.final_solution = "pakai playwright + BS4 fallback"
rec = experience.save_task_memory(t)
ok(experience.all_tasks() and rec["task_id"] == t.id, "1 task memory tersimpan (field lengkap)")
ok(rec["normalized_goal"] and rec["tags"] and rec["result"] == "success", "1 normalisasi+tags+result OK")
# backward compat: field v3.0 utuh
h = json.load(open(experience.HIST_FILE))[0]
ok(all(k in h for k in ("id", "goal", "state", "complexity", "steps", "tool_calls",
                        "repairs", "elapsed", "subtasks", "critic_status")),
   "1 entri kompatibel field v3.0 (super-set)")

# ── 2: retrieval ─────────────────────────────────────────────────────
r = experience.recall("Buat scraper produk dengan playwright")
ok(r["similar_tasks"] and r["similar_tasks"][0]["memory_id"] == t.id, "2 retrieval menemukan memori")

# ── 3: similar task detection (web A → web B) ───────────────────────
r2 = experience.recall("Buat scraper harga dengan playwright untuk web B")
sim = r2["similar_tasks"][0]
ok(sim["similarity"] >= 0.5 and sim["result"] == "success",
   f"3 task serupa terdeteksi lintas target (sim={sim['similarity']})")
r3 = experience.recall("resep nasi goreng")
ok(not r3["similar_tasks"], "3 task tidak serupa TIDAK recall (anti-halusinasi memori)")

# ── 4: failure memory ────────────────────────────────────────────────
t2 = orchestra.Task("deploy app ke vercel", client=None)
t2.state = "COMPLETED"; t2.plan = {"goal": "g", "subtasks": [{"id": "s1", "description": "x"}]}
t2.subtask_results = {"s1": {"status": "success", "actions": [], "files_changed": [],
                             "errors": [], "commands_executed": [], "tests": []}}
t2.debug_log = [{"error": "ECONNREFUSED", "root_cause": "path salah: sandbox bukan cwd proses",
                 "component": "exec", "fix_steps": ["pakai abspath"], "confidence": 0.9}]
t2.critic = {"status": "pass", "requirements_met": ["done"]}
t2.skill_report = None
experience.save_task_memory(t2)
fm = experience.all_failures()
ok(len(fm) == 1 and fm[0]["success_after_fix"] is True and fm[0]["failure_type"] == "path_error",
   "4 failure tercatat + fix terbukti (success_after_fix)")
ok(experience.recall_failures("eksekusi shell path"), "4 recall failure utk task terkait")

# ── 5: planner menerima konteks memori ──────────────────────────────
class StubLLM:
    last_finish_reason = None; last_usage = {}
    def __init__(self, responses): self.responses = responses
    def chat_failover(self, model, msgs, *a, **k):
        s = msgs[0]["content"] if msgs[0]["role"] == "system" else ""
        self.last_user = (msgs[1]["content"] if len(msgs) > 1 else "")
        key = ("Planner" if "Planner" in s else "Analyst" if "Skill Analyst" in s
               else "Critic" if "Critic" in s else "Debugger" if "Debugger" in s else "other")
        self.last_seen = s
        return (json.dumps(self.responses.get(key, "{}")), "stub")
    def chat(self, *a, **k): return {"error": "x"}
plan_resp = {"goal": "scraper web B", "complexity": "simple", "success_criteria": ["jalan"],
             "subtasks": [{"id": "s1", "description": "adapt scraper lama", "required_skills": [],
                           "required_tools": [], "depends_on": []}]}
tp = orchestra.Task("Buat scraper produk dengan playwright untuk web B", client=StubLLM({"Planner": plan_resp}))
tp.messages = []
experience.recall("x")  # ensure hist ada
orchestra.planner(tp)
ok("PENGALAMAN RELEVAN" in tp.client.last_user and "playwright" in tp.client.last_user,
   "5 planner di-inject pengalaman relevan dari memory")

# ── 6: dependency graph topo ─────────────────────────────────────────
subs = [{"id": "D", "depends_on": ["B", "C"]}, {"id": "A", "depends_on": []},
        {"id": "B", "depends_on": ["A"]}, {"id": "C", "depends_on": ["B"]}]
g = orchestra.graph_validate(subs)
ok(g["valid"] and g["order"].index("A") < g["order"].index("B") < g["order"].index("D"),
   f"6 topo order benar: {g['order']}")

# ── 7: cycle detection ───────────────────────────────────────────────
g2 = orchestra.graph_validate([{"id": "A", "depends_on": ["C"]}, {"id": "B", "depends_on": ["A"]},
                               {"id": "C", "depends_on": ["B"]}])
ok(not g2["valid"] and set(g2["cycle"]) == {"A", "B", "C"}, "7 cycle A→B→C→A terdeteksi + ditolak")
# run() dgn cycle → FAILED terikat (bukan gantung)
tc = orchestra.Task("task ber.cycle A dan B dan C dan D dan E dan F dan G dan H dan I dan J dan K dan L dan M dan N dan O dan P dan Q dan R dan S dan T dan U dan V dan W dan X dan Y dan Z dan A2 dan B2 dan C2 dan D2", client=StubLLM({
    "Planner": {"goal": "g", "complexity": "complex", "success_criteria": [],
                "subtasks": [{"id": "A", "description": "a", "depends_on": ["B"]},
                             {"id": "B", "description": "b", "depends_on": ["A"]}]},
    "Critic": {"status": "pass"}}))
tc.messages = []
orchestra.run(tc)
ok(tc.state == "FAILED" and "cycle" in (tc.error or ""), "7 run() cycle → FAILED bounded (graph ditolak)")

# ── 8: blocked subtask ───────────────────────────────────────────────
orig_exec = orchestra.executor
def fake_exec(task, st):
    s = {"success": {"status": "success", "actions": [], "files_changed": [],
                     "commands_executed": [], "errors": [], "tests": []},
         "failed": {"status": "failed", "actions": [], "files_changed": [],
                    "commands_executed": [], "errors": ["boom"], "tests": []}}
    return s["failed"] if st["id"] == "A" else s["success"]
orchestra.executor = fake_exec
tb = orchestra.Task("uji blocked", client=StubLLM({
    "Planner": {"goal": "g", "complexity": "simple", "success_criteria": [],
                "subtasks": [{"id": "A", "description": "a", "depends_on": []},
                             {"id": "B", "description": "b", "depends_on": ["A"]}]},
    "Critic": {"status": "pass"}}))
tb.messages = []
orchestra.run(tb)
ok(tb.sub_states.get("A") == "FAILED" and tb.sub_states.get("B") == "BLOCKED",
   "8 dep gagal → dependent BLOCKED (bukan jalan buta)")
orchestra.executor = orig_exec

# ── 9: ready/completed states ────────────────────────────────────────
ok(tb.sub_states and set(tb.sub_states.values()) <= set(orchestra.SUB_STATES),
   "9 semua sub-state legal (PENDING/READY/RUNNING/COMPLETED/FAILED/BLOCKED)")

# ── 10: skill health ─────────────────────────────────────────────────
def seed(layer, name):
    d = os.path.join(tools.SKILL_DIR, layer, name); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "SKILL.md"), "w").write(f"# {name}\n## Purpose\nuji {name}\n")
    tools._SKILL_INDEX = {}; tools._build_skill_index(); registry.ensure_seeded()
for i, nm in enumerate(["healthy", "degraded", "broken", "stale", "fresh"]):
    seed("v31", nm)
for i in range(4): registry.record_use(["v31/healthy"], True)
for i in range(2): registry.record_use(["v31/degraded"], True)
for i in range(2): registry.record_use(["v31/degraded"], False)
for i in range(4): registry.record_use(["v31/broken"], False)
registry.record_use(["v31/fresh"], True)
ok(registry.health("v31/healthy") == "HEALTHY", "10 health HEALTHY (confidence+recent+fresh)")
ok(registry.health("v31/degraded") == "DEGRADED", "10 health DEGRADED")
ok(registry.health("v31/broken") == "BROKEN", "10 health BROKEN")
ok(registry.health("v31/fresh") == "UNVERIFIED", "10 health UNVERIFIED (bukti kurang)")
# STALE: umur manual
d = registry._load_raw()
d["skills"]["v31/healthy"]["last_verified"] = "2020-01-01T00:00:00Z"
registry._save_raw(d)
ok(registry.health("v31/healthy") == "STALE", "10 health STALE (>=60hr tanpa verifikasi)")
ok(registry.get("v31/broken") is not None, "10 skill BROKEN tidak dihapus otomatis")

# ── 11: skill scoring + evidence ─────────────────────────────────────
for i in range(4): registry.record_use(["v31/healthy"], True)
rk = registry.rank("healthy", ["v31/healthy", "v31/broken"])
ok(rk and rk[0]["skill"] == "v31/healthy" and rk[0]["score"] > rk[-1]["score"],
   f"11 rank: bukti terbaik menang ({rk[0]['skill']}={rk[0]['score']} > {rk[-1]['skill']})")
ok(all("evidence" in r and r["evidence"] for r in rk), "11 setiap rank disertai bukti terstruktur")

# ── 12: recent vs lifetime ───────────────────────────────────────────
m = registry.get("v31/degraded")
ok(m.get("recent") and 0 < sum(m["recent"]) < len(m["recent"]),
   f"12 recent window terpisah dari lifetime (recent={m['recent']})")

# ── 13: stale detection ──────────────────────────────────────────────
d = registry._load_raw()
d["skills"]["v31/degraded"]["last_verified"] = "2020-01-01T00:00:00Z"
registry._save_raw(d)
ok(registry.health("v31/degraded") == "STALE", "13 stale skill terdeteksi (60hr tanpa verifikasi)")

# ── 14: memory confidence + 15: positive + 16: negative feedback ────
n0 = experience.all_tasks()[0]
experience.feedback(n0["id"], "success", memory_ids=[n0["id"]])
c1 = next(h for h in experience.all_tasks() if h["id"] == n0["id"])
ok(c1["mem_confidence"] > n0["mem_confidence"] and c1["reuse_success"] == 1, "15 feedback positif naikkan confidence")
experience.feedback(c1["id"], "failure", memory_ids=[c1["id"]], failure_reason="outdated API")
c2 = next(h for h in experience.all_tasks() if h["id"] == c1["id"])
ok(c2["mem_confidence"] < c1["mem_confidence"] and "outdated API" in json.dumps(c2),
   "16 feedback negatif turunkan confidence + rekam alasan")
c2b = experience.feedback(c2["id"], "success", memory_ids=[c2["id"]])
c3 = next(h for h in experience.all_tasks() if h["id"] == c2["id"])
ok(c3["mem_quality"] == "REUSABLE", "14/15 reuse sukses ≥2 → REUSABLE (quality control)")

# ── 17: metrics ──────────────────────────────────────────────────────
mt = experience.metrics()
ok(mt["tasks"] >= 2 and 0 <= mt["success_rate"] <= 1, "17 metrics task terhitung")
ok("memory_hit_rate" in mt and "failure_patterns" in mt and "avg_retries" in mt,
   "17 metrics lengkap (memory hit, failure patterns, retries)")
ok("memory_sample_warning" in mt, "17 kejujuran sampel kecil (anti-klaim palsu)")

# ── 18: loop safety masih aktif ──────────────────────────────────────
# v3.7.2: limit ada di orch_state.py / orch_scheduler.py, protection di orch_scheduler.py.
_src = "\n".join(open(f, encoding="utf-8", errors="replace").read()
                  for f in _glob.glob(os.path.join(os.path.dirname(__file__), "..", "core", "orch_*.py")))
ok(all(k in _src for k in ("max_retries", "max_repair_attempts", "max_tool_calls",
                          "max_agent_steps", "task.limits[\"timeout\"]")),
   "18 semua limit v3.0 tetap dirujuk")
ok("task.graph[\"valid\"]" in _src and "BLOCKED" in _src, "18 protection cycle+blocked di jalur run")

# ── 19: requality (STALE tua tanpa reuse) ────────────────────────────
hist = experience._load(experience.HIST_FILE)
hist[0]["created_at"] = "2020-01-01T00:00:00Z"; hist[0]["mem_quality"] = "CONFIRMED"
hist[0]["reuse_success"] = 0; hist[0]["reuse_failure"] = 0
experience._save(experience.HIST_FILE, hist)
n = experience.requality()
h0 = next(x for x in experience.all_tasks() if x["id"] == hist[0]["id"])
ok(h0["mem_quality"] == "STALE" and n >= 1, "19 requality → STALE utk memori tua tak terpakai")

print("\n" + ("ALL PASS" if fails == 0 else f"{fails} FAIL"))
sys.exit(1 if fails else 0)
