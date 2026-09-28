#!/usr/bin/env python3
"""tests/test_v38_plan_subagent.py — v3.8 plan mode + sub-agent paralel.
Deterministik, offline (stub LLM / monkeypatch)."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

LQ, GQ = chr(60), chr(62)


def T(s):
    """[[tag]] -> <tag>"""
    return s.replace("[[", LQ).replace("]]", GQ)


from core import config, planmode, subagents, tags, tools, tooldef  # noqa: E402

PASS, FAIL = 0, 0


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name} {extra}")


# ── 1. planmode heuristics (pure, offline) ───────────────────────────
check("1.1 task terdeteksi", planmode.is_task_like("buatkan script backup harian"))
check("1.2 chat bukan task", not planmode.is_task_like("halo apa kabar?"))
check("1.3 tanya pendek bukan task", not planmode.is_task_like("jam berapa sekarang?"))
check("1.4 command bukan task", not planmode.is_task_like("/model dahl-pool"))

check("2.1 approve 'gas'", planmode.check_approval("gas") == "approve")
check("2.2 approve 'ok gas bro'", planmode.check_approval("ok gas bro") == "approve")
check("2.3 reject 'batal aja'", planmode.check_approval("batal aja") == "reject")
check("2.4 revise teks bebas", planmode.check_approval("tambahin langkah testing") == "revise")

# mode off → tidak pernah draft
_old = config.PLAN_MODE
config.PLAN_MODE = "off"
check("3.1 mode off → no draft", not planmode.should_draft("buatkan bot telegram"))
config.PLAN_MODE = "auto"
check("3.2 auto + task → draft", planmode.should_draft("buatkan bot telegram"))
check("3.3 auto + chat → no draft", not planmode.should_draft("makasih banyak"))
check("3.4 approved → no draft", not planmode.should_draft("buatkan bot", plan_approved=True))
config.PLAN_MODE = "always"
check("3.5 always → draft", planmode.should_draft("hai"))
config.PLAN_MODE = _old

# ── 2. draft_plan dengan stub client ─────────────────────────────────
class _StubClient:
    def chat_failover(self, model, messages, chain, **kw):
        assert messages[0]["role"] == "system"
        return ("1. Riset dulu [PARALEL]\n2. Implementasi\n3. Test", "stub-model")


_saved_tool_plan = planmode.tools.tool_plan
_saved_plans = []
planmode.tools.tool_plan = lambda a, c=None: (_saved_plans.append((a, c)) or "OK stub")
try:
    plan_text, used = planmode.draft_plan("buatkan bot", client=_StubClient())
    check("4.1 draft_plan return teks", "Riset" in plan_text and used == "stub-model")
    check("4.2 draft_plan save ke tool_plan",
          _saved_plans and _saved_plans[0][0] == "save" and "buatkan bot" in _saved_plans[0][1])
finally:
    planmode.tools.tool_plan = _saved_tool_plan

# ── 3. spawn: parsing tasks ──────────────────────────────────────────
p1 = tools._parse_spawn_tasks('[{"name":"a","task":"kerjakan x"},{"name":"b","task":"kerjakan y"}]')
check("5.1 parse JSON list", len(p1) == 2 and p1[0]["name"] == "a" and p1[1]["task"] == "kerjakan y")
p2 = tools._parse_spawn_tasks("riset-a: cari info X\nriset-b | cari info Y")
check("5.2 parse baris nama: task", len(p2) == 2 and p2[0] == {"name": "riset-a", "task": "cari info X"})
check("5.3 parse kosong → []", tools._parse_spawn_tasks("") == [])

# ── 4. tooldef: spawn terdaftar ──────────────────────────────────────
check("6.1 spawn di TOOL_DEFS", "spawn" in tooldef.TOOL_DEFS)
check("6.2 spawn di EXEC_ORDER", "spawn" in tooldef.EXEC_ORDER)
clean, errors, warns = tooldef.validate("spawn", {"tasks": "a: x"})
check("6.3 validate spawn ok", not errors and clean["tasks"] == "a: x")
_c2, e2, _w2 = tooldef.validate("spawn", {})
check("6.4 validate spawn tanpa tasks → error", bool(e2))
check("6.5 alias subagent → spawn", tooldef.canon_tool("subagent") == "spawn")
_payload = tooldef.openai_tools()
check("6.6 openai_tools memuat spawn",
      any(t["function"]["name"] == "spawn" for t in _payload))

# ── 5. tags dispatch <spawn> (stub subagents.spawn) ──────────────────
_saved_spawn = subagents.spawn
_calls = []
subagents.spawn = lambda tasks, max_rounds=None: (_calls.append((tasks, max_rounds))
                                                  or "[stub] agregat")
try:
    out = tags.dispatch(T("[[spawn tasks='riset-a: cari X' /]]"), config.SELF_PATH)
    check("7.1 dispatch spawn jalan", "[spawn]" in out and "[stub] agregat" in out)
    check("7.2 tasks ter-parse ke subagents",
          _calls and _calls[0][0][0] == {"name": "riset-a", "task": "cari X"})
finally:
    subagents.spawn = _saved_spawn

# ── 6. depth guard: sub-agent tidak boleh spawn lagi ─────────────────
subagents._DEPTH.n = 1
try:
    out2 = tools.tool_spawn("a: x")
    check("8.1 spawn di dalam sub-agent ditolak", "ERROR" in out2 and "tidak boleh" in out2)
finally:
    subagents._DEPTH.n = 0

# ── 7. spawn paralel beneran jalan bareng (stub run_one) ──────────────
import time as _time
_saved_run_one = subagents.run_one
_started = []


def _fake_run_one(name, task, model, max_rounds, timeout_s=600):
    _started.append((name, _time.time()))
    _time.sleep(0.3)
    return f"[{name}] done"


subagents.run_one = _fake_run_one
try:
    t0 = _time.time()
    agg = subagents.spawn([{"name": "a", "task": "x"}, {"name": "b", "task": "y"}],
                          max_workers=2)
    dt = _time.time() - t0
    check("9.1 agregat berisi semua hasil", "[a] done" in agg and "[b] done" in agg)
    check("9.2 paralel (2x0.3s < 0.55s)", dt < 0.55, f"dt={dt:.2f}s")
    check("9.3 maks 8 sub-agent", "maks 8" in subagents.spawn([{"name": str(i), "task": "x"} for i in range(9)]))
finally:
    subagents.run_one = _saved_run_one

print(f"\nRESULT: {PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
