#!/usr/bin/env python3
# tests/perf_v32.py — Phase 5: bukti kinerja paralel vs serial (deterministik, tanpa LLM).
import os, sys, time, tempfile, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import orchestra, experience, registry, tools

TMP = tempfile.mkdtemp(prefix="lx-perf-")
experience.HIST_FILE = os.path.join(TMP, "h.json")
experience.FAIL_FILE = os.path.join(TMP, "f.json")
registry.REG_FILE = os.path.join(TMP, "r.json")
tools.SKILL_DIR = os.path.join(TMP, "s"); os.makedirs(tools.SKILL_DIR)

import json
class StubLLM:
    last_finish_reason=None; last_usage={}
    def __init__(s,r): s.r=r
    def chat_failover(s,m,msgs,*a,**k):
        sy=msgs[0]["content"] if msgs[0]["role"]=="system" else ""
        key="Planner" if "Planner" in sy else "Critic" if "Critic" in sy else "other"
        return (json.dumps(s.r.get(key,"{}")),"stub")
    def chat(s,*a,**k): return {"error":"x"}

PLAN = {"goal":"g","complexity":"complex","success_criteria":[],
        "subtasks":[{"id":"A","description":"riset X","depends_on":[]},
                    {"id":"B","description":"riset Y","depends_on":[]},
                    {"id":"C","description":"riset Z","depends_on":[]},
                    {"id":"D","description":"integri","depends_on":["A","B","C"]}]}
TICK = 0.6
peak = [0]; lk = threading.Lock()
def work(task, st):
    with lk:
        with task.lock:
            peak[0] = max(peak[0], sum(1 for v in task.sub_states.values() if v=="RUNNING"))
    time.sleep(TICK)
    return {"status":"success","actions":[],"files_changed":[],
            "commands_executed":[],"errors":[],"tests":[],"reply_tail":"ok"}
orchestra.executor = work

def run_case(maxc):
    global peak
    peak = [0]
    t = orchestra.Task("perf", client=StubLLM({"Planner":PLAN,
        "Critic":{"status":"pass","requirements_met":["ok"],"requirements_failed":[],
                  "bugs":[],"recommendation":"complete"}}))
    t.messages=[]; t.limits=dict(t.limits); t.limits["max_concurrent_agents"]=maxc
    t0=time.time(); orchestra.run(t); dur=time.time()-t0
    return t, dur, peak[0]

ts, ds, pk_s = run_case(1)
tp, dp, pk_p = run_case(3)
# D menunggu → par: max(TICK) + TICK = 2*TICK ; serial: 4*TICK
print(f"serial   : {ds:.2f}s  peak_conc={pk_s}  (4×{TICK}s = {4*TICK}s theoretical)")
print(f"parallel : {dp:.2f}s  peak_conc={pk_p}  (2×{TICK}s = {2*TICK}s theoretical)")
print(f"speedup  : {ds/dp:.2f}x   (baseline serial NYATA, bukan fabrikasi)")
okc = []
okc.append(("D menunggu A+B+C", tp.sub_states["D"]=="COMPLETED" and dp >= 2*TICK*0.8 and dp < 3*TICK))
okc.append(("peak concurrency ≤ 3", pk_p <= 3 and pk_p >= 2))
okc.append(("serial tidak paralel", pk_s <= 1))
okc.append(("state final benar", tp.state=="COMPLETED" and ts.state=="COMPLETED"))
okc.append(("speedup realistis ~2x", 1.5 <= ds/dp <= 2.6))
okc.append(("stats paralel tercatat", tp.parallel_stats["parallel"] and tp.parallel_stats["max_concurrency"]>=2))
for name, c in okc: print(("PASS" if c else "FAIL") + " - " + name)
print("\n" + ("PERF OK" if all(c for _,c in okc) else "PERF FAIL"))
sys.exit(0 if all(c for _,c in okc) else 1)
