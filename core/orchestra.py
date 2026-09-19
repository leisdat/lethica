# core/orchestra.py — v3.0 Orchestrator multi-agent ber-state eksplisit.
#
#     CORE ─→ PLANNER ─→ SKILL ANALYST ─(missing?)→ RESEARCHER → BUILDER → EVALUATOR
#      └──────────────→ EXECUTOR (loop tools yang SUDAH ADA) → CRITIC ─PASS→ DONE
#                                                        └─FAIL→ DEBUGGER → REPAIR → CRITIC
#
# Prinsip: modul ini Mendelegasikan, bukan mengerjakan sendiri. Eksekusi memakai
# tags.dispatch yang sudah ada; verifikasi memakai _reflect-style evidence check;
# learning signal ke core.registry (bukan prompt). Semua state terstruktur.
import os
import re
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from core import config, client as client_mod, tools, tags, rag, registry, soul, experience
from core import strategy as strategy_mod
from core import evolution

SUB_STATES = ["PENDING", "READY", "RUNNING", "COMPLETED", "FAILED", "BLOCKED", "CANCELLED"]


# ── task states (ekslisit, terstruktur) ─────────────────────────────
STATES = ["RECEIVED", "PLANNING", "SKILL_ANALYSIS", "RESEARCHING", "EXECUTING",
          "VERIFYING", "DEBUGGING", "REPAIRING", "COMPLETED", "FAILED"]

LOG_FILE = os.path.join(config.LOG_DIR, "orchestra.log")
HIST_FILE = os.path.join(config.LETHICA_DIR, "task-history.json")


def _log(tag, msg, task_id=None):
    tid = f" task={task_id}" if task_id else ""
    line = f"[{time.strftime('%H:%M:%S')}]{tid} [{tag}] {msg}"
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        from core.ui import console
        console.print(f"[dim]{line}[/dim]")
    except Exception:
        print(line)


def _limits():
    g = config.CFG.get("orchestra", {})
    g.setdefault("sub_agent_max_tokens", 1500)
    return {
        "max_agent_steps": int(g.get("max_agent_steps", 12)),
        "max_retries": int(g.get("max_retries", 2)),
        "max_repair_attempts": int(g.get("max_repair_attempts", 2)),
        "timeout": int(g.get("timeout", 1800)),
        "max_tool_calls": int(g.get("max_tool_calls", 40)),
        # v3.2 concurrency budget (default konservatif)
        "max_concurrent_agents": max(1, int(g.get("max_concurrent_agents", 3))),
        "max_total_agent_calls": int(g.get("max_total_agent_calls", 60)),
        "max_subtasks": int(g.get("max_subtasks", 5)),
    }


class Task:
    """State terstruktur satu task. Bukan natural-language."""

    def __init__(self, goal, client=None, model=None):
        self.id = time.strftime("%Y%m%d-%H%M%S") + "-" + re.sub(r"\W+", "", goal[:20]).lower()
        self.goal = goal
        self.state = "RECEIVED"
        self.complexity = "simple"          # simple | complex (auto)
        self.plan = None                    # output Planner
        self.skill_report = None            # output Skill Analyst
        self.research_notes = []
        self.subtask_results = {}           # id → executor result dict
        self.critic = None                  # output Critic terakhir
        self.debug_log = []                 # output Debugger
        self.repair_count = 0
        self.tool_calls = 0
        self.messages = [{"role": "system", "content": soul.build_system_prompt()}]
        self.client = client
        self.model = model
        self.limits = _limits()
        self.t0 = time.time()
        self.steps = 0
        self.error = None
        # v3.1 experience-aware
        self.lock = threading.Lock()  # v3.2: state utk worker paralel
        self.cancelled = False        # v3.2: flag bounded cancellation
        self.merged = None            # v3.2: output Result Merger
        self.parallel_stats = {"parallel": False, "max_concurrency": 0,
                               "parallel_tasks": 0, "conflicts": 0, "cancellations": 0}
        self.recalled = []           # hasil recall utk planner
        self.recalled_ids = []
        self.sub_states = {}         # subtask id → SUB_STATES
        self.parent_id = None
        self.final_solution = ""
        self.graph = None
        # v3.4 controlled skill evolution evidence
        self.skill_gaps = []
        self.skill_evolution = []
        # v3.3 adaptive planning (strategy is data, not another agent)
        self.semantic_memories = []      # v3.5: memori semantic ter-rank
        self.semantic_scores = []
        self.graph_context = ""          # v3.6: blok konteks knowledge graph
        self.graph_entities = []
        self.graph_paths = []
        self.world_state = None          # v3.6: snapshot world model project
        self.graph_trace = None          # v3.6: jejak update graph (bukti)
        self.strategy_candidates = []
        self.strategy_selection = None
        self.strategy = None
        self.strategy_confidence = "LOW"
        self.strategy_switches = 0
        self.strategy_history = []
        self.strategy_failure = None
        self.planning_metrics = {"strategy_candidates_generated": 0,
                                 "strategy_selected": 0, "strategy_exploration": 0,
                                 "strategy_selection_latency": 0.0,
                                 "planning_latency": 0.0, "execution_latency": 0.0,
                                 "total_latency": 0.0}

    def transition(self, new_state):
        assert new_state in STATES, f"state tidak dikenal: {new_state}"
        _log("CORE", f"{self.state} → {new_state}", self.id)
        self.state = new_state
        self.steps += 1

    def elapsed(self):
        return time.time() - self.t0

    def to_dict(self):
        return {"id": self.id, "goal": self.goal[:200], "state": self.state,
                "complexity": self.complexity, "steps": self.steps,
                "tool_calls": self.tool_calls, "repairs": self.repair_count,
                "elapsed": round(self.elapsed(), 1),
                "subtasks": len((self.plan or {}).get("subtasks", [])),
                "critic_status": (self.critic or {}).get("status"),
                "memory_used": self.recalled_ids,
                "sub_states": self.sub_states,
                "strategy_id": self.strategy.id if self.strategy else None,
                "strategy_confidence": self.strategy_confidence,
                "strategy_switches": self.strategy_switches,
                "planning_metrics": self.planning_metrics,
                "error": self.error}


# ── LLM helper: satu panggilan, parse JSON, fallback robust ─────────
def _ask_json(task, system, user, max_tokens=900):
    cl = task.client or client_mod.LClient()
    max_tokens = min(max_tokens, getattr(config, "ORCHESTRA_SUB_MAX_TOKENS", 900))
    task.agent_calls = getattr(task, "agent_calls", 0) + 1  # v3.2: hit ke budget
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    out = {}
    try:
        r = cl.chat_failover(task.model or config.DEFAULT_MODEL, msgs,
                             config.FAILOVER_CHAIN, timeout=min(config.HTTP_TIMEOUT, 90),
                             temperature=0.2, max_tokens=max_tokens)
        reply = (r[0] if isinstance(r, tuple) else r) or ""
        m = re.search(r"\{[\s\S]*\}", reply)
        if m:
            try:
                out = json.loads(m.group(0))
            except Exception:
                from core import json_tools
                fixed = json_tools.normalize_json_tool_calls(m.group(0)) if hasattr(json_tools, "normalize_json_tool_calls") else m.group(0)
                try:
                    out = json.loads(fixed)
                except Exception:
                    out = {}
    except Exception as ex:
        _log("CORE", f"LLM JSON call gagal: {ex}")
    return out


def _skill_index_snippet():
    """Katalog layer asli (bukan tebakan) utk Planner/Analyst."""
    try:
        tools._build_skill_index()
        return tools._skill_list()[:3000]
    except Exception:
        return "(skill index kosong)"


# ── PLANNER ──────────────────────────────────────────────────────────
def planner(task):
    task.transition("PLANNING")
    # v3.1 FEATURE 2/4: recall dulu → pengalaman sebagai BUKTI ke planner
    mem = experience.recall(task.goal)
    task.recalled = mem["similar_tasks"]
    task.recalled_ids = [m["memory_id"] for m in task.recalled]
    task.failure_patterns = experience.recall_failures(task.goal)
    fails = task.failure_patterns
    if task.recalled:
        _log("MEMORY", f"hits={len(task.recalled)} top_sim={task.recalled[0]['similarity']}", task.id)
    if fails:
        _log("MEMORY", f"failure_patterns={len(fails)}", task.id)
    # v3.5 SEMANTIC LONG-TERM MEMORY (Phase 26): retrieval hybrid berdampingan
    # dengan experience.recall — TIDAK mengganti, hanya menambah konteks.
    try:
        import core.memory as semantic_mem
        smem = semantic_mem.retrieve_for_plan(
            task.goal,
            project_id=getattr(task, "project_id", None),
            skill_id=(getattr(task, "skill_report", {}) or {}).get("active_skill"),
            strategy_id=getattr(getattr(task, "strategy", None), "id", None),
            task_id=task.id, top_k=5)
        task.semantic_memories = smem["memories"]
        task.semantic_scores = smem["scores"]
        if smem["similar_tasks"]:
            _log("MEMORY", f"v3.5 semantic hits={len(smem['similar_tasks'])} top_rel={smem['similar_tasks'][0]['relevance']}", task.id)
    except Exception as ex:
        task.semantic_memories = []
        task.semantic_scores = []
        _log("MEMORY", f"v3.5 semantic unavailable: {ex}", task.id)
    # v3.6 KNOWLEDGE GRAPH + WORLD MODEL (Phase 29): context relasional + state project.
    # Advisory saja — planner WAJIB verifikasi asumsi kritis. Gagal = no-op (non-breaking).
    task.graph_context = ""
    task.world_state = None
    try:
        from core import relation as graph_rel, world as world_mod
        block, gres = graph_rel.context_block(
            task.goal, project_id=getattr(task, "project_id", None), top_k=4)
        task.graph_context = block
        task.graph_entities = gres.get("seed_entities", [])
        task.graph_paths = gres.get("graph_paths", [])
        if task.graph_entities:
            _log("GRAPH", f"v3.6 entities={len(task.graph_entities)} "
                 f"paths={len(task.graph_paths)} nodes={len(gres.get('graph_nodes', []))}", task.id)
        if getattr(task, "project_id", None):
            task.world_state = world_mod.get_project_state(task.project_id)
            _log("GRAPH", f"v3.6 world state: components={task.world_state.get('nodes')} "
                 f"stale={len(task.world_state.get('stale') or [])}", task.id)
    except Exception as ex:
        task.graph_context = ""
        task.world_state = None
        _log("GRAPH", f"v3.6 graph context unavailable: {ex}", task.id)
    ctx = ""
    if task.recalled:
        ctx += "\nPENGALAMAN RELEVAN (bukti, bukan kebenaran — verifikasi lagi):\n" + "\n".join(
            f"- [{m['similarity']}] {m['goal']} → {m['result']}; approach: {m['approach'][:3]}; "
            f"kualitas={m['mem_quality']} conf={m['mem_confidence']}"
            for m in task.recalled)
    if task.semantic_memories:
        ctx += "\nMEMORI SEMANTIC v3.5 (relevansi ter-rank, verifikasi sebelum pakai):\n" + "\n".join(
            f"- [{s['relevance']:.2f}|{m.get('type')}|{m.get('quality')}] {m.get('title','')[:80]}"
            f" :: {m.get('content','')[:160]}"
            for s, m in zip(task.semantic_scores, task.semantic_memories))
    if getattr(task, "graph_context", ""):
        ctx += ("\nKNOWLEDGE GRAPH v3.6 (entity + relasi eksplisit + memori ter-rank; "
                "relasi HANYA yang ber-evidence, korelasi bukan kausalitas):\n"
                + task.graph_context[:1800])
    if getattr(task, "world_state", None):
        ws = task.world_state or {}
        ctx += (f"\nWORLD MODEL v3.6 [{ws.get('project')}]: status={ws.get('status')} "
                f"freshness={ws.get('freshness')} components={ws.get('nodes')} "
                f"stale={ws.get('stale')} conflicted={ws.get('conflicted')}")
    if fails:
        ctx += "\nPOLA FAILURE TERKENAL (hindari / siapkan mitigasi):\n" + "\n".join(
            f"- {f['failure_type']} @ {f['context'][:60]}: {f['root_cause'][:100]} → fix: {f['fix']}"[:200]
            for f in fails)
    # heuristic dulu: task pendek/aksi tunggal tidak perlu subtask
    simple = len(task.goal) < 160 and not re.search(
        r"\bdan\b|\blalu\b|\bsetelah itu\b|\bberbagai\b|\bmulti\b|lalu|kemudian",
        task.goal, re.I)
    plan = _ask_json(
        task,
        "Kamu Planner agent. Ubah task jadi subtask tereksekusi. Balas HANYA JSON: "
        '{"goal":str,"complexity":"simple|medium|complex","success_criteria":[str],'
        '"subtasks":[{"id":"s1","description":str,"required_skills":[str],'
        '"required_tools":[str],"depends_on":[str]}],'
        '"risks":[str],"reused_experience":[str]}. '
        "JANGAN bikin subtask yang tidak perlu. Max 5 subtask. "
        "PARALEL: jika task menyebut beberapa bagian BEBAS/saling independen, "
        "PECAH jadi subtask terpisah dengan depends_on [] agar scheduler bisa "
        "menjalankannya bersamaan — JANGAN gabungkan jadi satu subtask raksasa. "
        "Pakai complexity complex bila >1 subtask. "
        "WAJIB: nyatakan dependensi antar subtask secara eksplisit (depends_on). "
        "PENTING: subtask HARUS dibuat dari TASK USER saat ini — DILARANG menyalin "
        "goal/paths dari blok PENGALAMAN RELEVAN (pakai hanya sebagai pola pendekatan). "
        f"Tools tersedia: {', '.join(sorted(tags.TAG_NAMES))}. "
        f"Skill layer tersedia (ASLI):\n{_skill_index_snippet()}",
        f"TASK USER:\n{task.goal}{ctx}")
    if not plan or not plan.get("goal"):
        plan = {"goal": task.goal, "complexity": "simple", "success_criteria": ["hasil valid"],
                "subtasks": [{"id": "s1", "description": task.goal,
                              "required_skills": [], "required_tools": [], "dependencies": []}]}
    # heuristik hemat: goal pendek → satu subtask, TAPI hanya utk mode serial —
    # v3.2: mode paralel menghormati dekomposisi planner (nodes independen = peluang paralel)
    if simple and len(plan.get("subtasks", [])) > 2 \
            and _limits().get("max_concurrent_agents", 3) <= 1:
        plan["subtasks"] = plan["subtasks"][:1]
        plan["complexity"] = "simple"
    plan.setdefault("complexity", "simple")
    task.complexity = plan["complexity"]
    task.plan = plan
    _log("PLANNER", f"subtasks={len(plan['subtasks'])} complexity={task.complexity}", task.id)
    return plan


# ── SKILL ANALYST ────────────────────────────────────────────────────
def skill_analyst(task):
    task.transition("SKILL_ANALYSIS")
    req = set()
    for st in task.plan.get("subtasks", []):
        req.update(st.get("required_skills", []) or [])
    if not req and task.complexity == "complex":  # minta model sebutkan sekali (murah), cocokkan vs registry ASLI
        guess = _ask_json(task,
                          "Kamu Skill Analyst. Sebutkan kemampuan yang dibutuhkan task ini. "
                          'Balas HANYA JSON: {"capabilities":[str]} (max 8, lowercase, tanpa spasi).',
                          task.plan.get("goal", task.goal), max_tokens=300)
        req.update(guess.get("capabilities", []))
    report = registry.analyze(sorted(req))
    task.skill_report = report
    task.skill_gaps = evolution.detect_gaps(task.id, sorted(req))
    task.plan.setdefault("skill_gaps", [g.to_dict() for g in task.skill_gaps])
    _log("SKILL", f"required={len(report['required_skills'])} "
                  f"available={len(report['available_skills'])} "
                  f"missing={len(report['missing_skills'])} action={report['action']}", task.id)
    registry.ensure_seeded()
    # skill yang dipakai di-analisa dapat exposure usage-count ringan: HANYA success utk available
    registry.record_use(report["available_skills"], success=True)
    return report


# ── v3.3 ADAPTIVE STRATEGY LAYER ────────────────────────────────────
def adaptive_strategy(task):
    """Generate, score, and select strategy data before DAG execution.

    The existing Planner still owns subtask decomposition and the existing DAG
    validator remains authoritative.  This layer only annotates that plan and
    supplies bounded fallback choices; it never authorizes tools.
    """
    started = time.time()
    if not strategy_mod._cfg().get("enabled", True):
        task.strategy_selection = {"selected": None, "confidence": "LOW",
                                   "reasoning": ["adaptive planning disabled"]}
        task.planning_metrics["planning_latency"] = round(time.time() - started, 4)
        return None
    level = strategy_mod.classify_complexity(task.goal)
    candidates = strategy_mod.generate_candidates(task.goal, level)
    task.strategy_candidates = candidates
    task.planning_metrics["strategy_candidates_generated"] = len(candidates)
    selected = strategy_mod.select_strategy(
        candidates, task.goal, memories=task.recalled,
        failures=getattr(task, "failure_patterns", []),
        skill_report=task.skill_report, task_id=task.id,
        available_tools=set(tags.TAG_NAMES))
    chosen = selected.get("selected")
    task.strategy_selection = _strategy_decision_payload(selected)
    if chosen:
        task.strategy = chosen
        task.strategy_history = [chosen.id]
        task.strategy_confidence = selected.get("confidence", "LOW")
        task.planning_metrics["strategy_selected"] = 1
        task.planning_metrics["strategy_exploration"] = int(selected.get("explored", False))
        task.plan.setdefault("adaptive_planning", {})
        task.plan["adaptive_planning"].update({
            "strategy_id": chosen.id,
            "strategy_name": chosen.name,
            "execution_style": chosen.execution_style,
            "confidence": task.strategy_confidence,
            "evidence_level": selected.get("evidence_level", "LOW"),
            "reasoning": selected.get("reasoning", []),
            "evidence": selected.get("evidence", []),
            "candidates": [c.id for c in candidates],
        })
        strategy_mod.REGISTRY.record_usage(chosen.id, selected.get("evidence", []))
        _log("STRATEGY", f"selected={chosen.id} confidence={task.strategy_confidence} "
             f"candidates={len(candidates)} explored={selected.get('explored', False)}", task.id)
    task.planning_metrics["strategy_selection_latency"] = round(time.time() - started, 4)
    task.planning_metrics["planning_latency"] = round(time.time() - task.t0, 4)
    return chosen


def _strategy_decision_payload(decision):
    """JSON-safe observability payload; internal Strategy objects stay private."""
    out = {k: v for k, v in decision.items() if k not in ("selected", "ranked")}
    selected = decision.get("selected")
    out["selected"] = selected.to_dict() if hasattr(selected, "to_dict") else selected
    out["ranked"] = []
    for row in decision.get("ranked", []):
        item = dict(row)
        obj = item.get("strategy")
        item["strategy"] = obj.to_dict() if hasattr(obj, "to_dict") else obj
        out["ranked"].append(item)
    return out


def _switch_strategy(task):
    """Bounded fallback after failure; prevents A→B→A oscillation."""
    cfg = strategy_mod._cfg()
    if task.strategy_switches >= cfg["max_strategy_switches"]:
        return False
    tried = set(task.strategy_history)
    available = [c for c in task.strategy_candidates if c.id not in tried]
    if not available:
        return False
    decision = strategy_mod.select_strategy(available, task.goal,
        memories=task.recalled, failures=getattr(task, "failure_patterns", []),
        skill_report=task.skill_report, tried=tried, task_id=task.id,
        available_tools=set(tags.TAG_NAMES))
    chosen = decision.get("selected")
    if not chosen:
        return False
    old = task.strategy.id if task.strategy else "none"
    task.strategy_switches += 1
    task.strategy = chosen
    task.strategy_history.append(chosen.id)
    task.strategy_selection = _strategy_decision_payload(decision)
    task.strategy_confidence = decision.get("confidence", "LOW")
    task.strategy_failure = strategy_mod.classify_failure(task, task.critic)
    task.plan.setdefault("adaptive_planning", {}).update({
        "strategy_id": chosen.id, "strategy_name": chosen.name,
        "confidence": task.strategy_confidence, "fallback_from": old,
        "switches": task.strategy_switches, "reasoning": decision.get("reasoning", []),
        "evidence": decision.get("evidence", []),
    })
    strategy_mod.REGISTRY.record_usage(chosen.id, decision.get("evidence", []))
    _log("STRATEGY", f"switch {old}→{chosen.id} reason={task.strategy_failure['classification']}", task.id)
    # Keep the same validated DAG; reset only execution results/state.
    task.subtask_results.clear()
    task.sub_states = {st["id"]: "PENDING" for st in task.plan.get("subtasks", [])}
    task.merged = None
    task.critic = None
    byid = {st["id"]: st for st in task.plan.get("subtasks", [])}
    if task.limits.get("max_concurrent_agents", 1) <= 1 or len(byid) <= 1:
        _execute_serial(task, byid)
    else:
        _execute_parallel(task, byid)
    merge_results(task)
    return True


# ── RESEARCHER ───────────────────────────────────────────────────────
def researcher(task):
    task.transition("RESEARCHING")
    # hanya skill HILANG yang diriset+digabung; outdated = sinyal update, jangan rebuild buta
    need = task.skill_report["missing_skills"]
    for cap in need[:3]:
        notes = {"capability": cap, "ts": time.strftime("%Y-%m-%d %H:%M")}
        try:
            sr = tools.tool_web_search(f"{cap} best practices official documentation", limit=3)
            notes["search"] = sr[:1500]
            for u in re.findall(r"https?://[^\s)\]]+", sr)[:2]:
                notes.setdefault("pages", []).append(
                    {"url": u[:120], "summary": tools.tool_browse(u)[:800]})
        except Exception as ex:
            notes["error"] = str(ex)[:150]
        task.research_notes.append(notes)
        _log("RESEARCH", f"riset '{cap}' ({len(notes.get('pages', []))} sumber)", task.id)
        # v3.6: riset → SOURCE + SUPPORTS edge (Phase 31). LOW confidence, bukan kebenaran permanen.
        try:
            from core import capture as graph_capture
            results = [{"url": p.get("url"), "title": p.get("url"), "snippet": p.get("summary")}
                       for p in notes.get("pages", [])]
            if notes.get("search") and not results:
                results = [{"title": f"search: {cap}", "snippet": notes["search"][:300]}]
            trace = graph_capture.record_research(
                cap, results, project_id=getattr(task, "project_id", None), task_id=task.id)
            if trace["sources"]:
                _log("GRAPH", f"v3.6 research sources={trace['sources']} supports={trace['supports']}", task.id)
        except Exception as ex:
            _log("GRAPH", f"v3.6 research sink skipped: {ex}", task.id)
    return task.research_notes


# ── SKILL BUILDER (research → skill → evaluator → register) ──────────
def build_missing_skills(task):
    for note in task.research_notes:
        cap = note["capability"]
        name = re.sub(r"[^a-z0-9]+", "-", cap.lower()).strip("-")[:40] or "unknown"
        research_evidence = [{"type": "research", "capability": cap,
                              "source": p.get("url"),
                              "summary": p.get("summary", "")[:240]}
                             for p in note.get("pages", []) if p.get("url")]
        proposal = evolution.SkillProposal(
            name=name, purpose=f"auto-generated utk kemampuan '{cap}'",
            capabilities=[cap], tools=["web_search", "browse"],
            security_level="LOW", implementation_plan=["research-backed SKILL.md"],
            test_plan=[], mode="CREATE", evidence=research_evidence)
        proposal_check = evolution.propose(proposal, task.id, research_evidence)
        task.skill_evolution.append({"capability": cap, "proposal": proposal.to_dict(),
                                     "proposal_check": proposal_check,
                                     "stage": "PROPOSED", "evidence": research_evidence})
        content = (f"## Purpose\nSkill generated utk kemampuan '{cap}'.\n\n"
                   "## Langkah\n" + "\n".join(
                       f"- sumber {p['url']}: {p['summary'][:200]}"
                       for p in note.get("pages", []))[:4000] +
                   f"\n\n## Catatan riset\n{note.get('search','')[:1500]}")
        r = registry.build_skill(name, "generated", content,
                                 description=f"auto-generated utk '{cap}'", capabilities=[cap])
        # Compatibility bridge: legacy builder remains unverified and is never
        # promoted implicitly. v3.4 lifecycle evidence records this boundary.
        task.skill_evolution[-1].update({"legacy_builder": r,
                                         "stage": "UNVERIFIED_LEGACY_COMPAT"})
        _log("BUILDER", f"skill '{r.get('skill', r.get('error'))}' (status: unverified)", task.id)
    return task.research_notes


# ── EXECUTOR (pakai loop tools asli) ─────────────────────────────────
def executor(task, subtask):
    prompt = (f"SUBTASK ({subtask['id']}): {subtask['description']}\n"
              f"Dari task besar: {task.plan.get('goal', task.goal)}\n"
              f"Skill relevan: {', '.join(subtask.get('required_skills', [])) or '-'}\n"
              "Kerjakan SEKARANG pakai tool. Akhiri dengan ringkasan bukti: file berubah, "
              "perintah dijalankan, hasil test.")
    task.messages.append({"role": "user", "content": prompt})
    used = {"n": 0}
    res = _run_tools(task, used)
    task.tool_calls += used["n"]
    out = {"status": "partial", "actions": [], "files_changed": [],
           "commands_executed": [], "tests": [], "errors": []}
    reply = res.get("reply", "")
    m = re.search(r"STATUS\s*[:=]\s*(success|partial|failed)", reply, re.I)
    out["status"] = m.group(1).lower() if m else ("success" if res.get("had_tools") else "failed")
    out["actions"] = res.get("actions", [])[:20]
    out["files_changed"] = res.get("files", [])[:20]
    out["commands_executed"] = res.get("cmds", [])[:20]
    out["errors"] = [e for e in res.get("err", []) if e][:8]
    out["reply_tail"] = (reply or "")[-400:]
    return out


def _scan_cmd_files(body, files):
    """v3.2: kumpulkan bukti file dari command (heredoc/redirect/touch).
    Path relatif di-resolve sadar-`cd` dalam command; glob basename HANYA di
    bawah cwd command (bukan seluruh WORKSPACE) — glob rekursif global dulu
    menyeret README.md project lain sbg false-positive artefak."""
    import glob as _glob
    cwd = config.WORKSPACE
    for mcd in re.finditer(r"\bcd\s+[\"']?([\w~./-]+)", body):
        d = os.path.abspath(os.path.expanduser(mcd.group(1)))
        if os.path.isdir(d):
            cwd = d
    # v3.2-fix: HANYA target tulis (>, >>, touch, tee, cp/mv arg terakhir) yang
    # jadi bukti artefak. File yang cuma DISEBUT (find/ls/cat/wc/grep) bukan
    # artefak — dulu ikut tercatat dan mencemari bukti Critic + prediksi konflik.
    cands_t = re.findall(
        r"(?:(?:>>|1>|2>|>)|\btouch\s+|\btee\s+(?:-a\s+)?"
        r"|\bcp\s+\S+\s+|\bmv\s+\S+\s+|\bmkdir\s+-p\s+)"
        r"[\"']?\s*([\w~][\w./-]*\.\w{1,4})", body)
    for cand in cands_t:
        if any(x in cand for x in ("/proc/", "/sys/", "/dev/")):
            continue
        ec = os.path.expanduser(cand)
        base = os.path.basename(cand)
        cands = [os.path.abspath(os.path.join(cwd, ec)), os.path.abspath(ec),
                 os.path.abspath(os.path.join(config.WORKSPACE, ec))]
        if len(base) > 3 and not os.path.isabs(ec):
            cands += _glob.glob(os.path.join(cwd, "**", base), recursive=True)
        for ap in cands:
            if os.path.isfile(ap):
                rel = (ap[len(config.WORKSPACE) + 1:]
                       if ap.startswith(config.WORKSPACE) else ap)
                if rel not in files:
                    files.append(rel)
                    break


def _run_tools(task, counter):
    """Mini replika run_agent_turn utk SATU subtask — pakai dispatch yang sama,
    tapi tanpa UI render & dengan hitung tool-call + kumpulkan bukti."""
    cl = task.client or client_mod.LClient()
    model = task.model or config.DEFAULT_MODEL
    max_rounds = max(2, min(task.limits["max_agent_steps"], 8))
    reply, actions, files, cmds, errs = "", [], [], [], []
    had = False
    nudged = False
    for _ in range(max_rounds):
        if task.elapsed() > task.limits["timeout"] or task.tool_calls + counter["n"] >= task.limits["max_tool_calls"]:
            errs.append("limit orchestra tercapai (step/tool/waktu)")
            break
        r = cl.chat_failover(model, task.messages, config.FAILOVER_CHAIN,
                             timeout=min(config.HTTP_TIMEOUT, 120),
                             max_tokens=task.limits.get("sub_agent_max_tokens", 1500))
        reply = r[0] if isinstance(r, tuple) else r
        if reply is None:
            errs.append("all models failed")
            break
        task.messages.append({"role": "assistant", "content": reply})
        out = tags.dispatch(reply, config.SELF_PATH)
        counter["n"] += len(re.findall(r"\[(?:read_file|write_file|edit_file|list_dir|search_content|http_request|download_file|web_search|browse|execute_command|run_code|skill|plan|rag|memory)\]", out or ""))
        if out:
            had = True
            for mm in re.finditer(r"\[(\w+)\]\n([\s\S]*?)(?=\n\n\[|$)", out):
                tool_name, body = mm.group(1), mm.group(2)
                actions.append(f"{tool_name}: {body[:250]}")
                if tool_name in ("write_file", "edit_file"):
                    mp = re.search(r"wrote to\s+(\S+)", body)
                    files.append(mp.group(1) if mp else body[:120])
                if tool_name == "execute_command":
                    cmds.append(body[:120])
                    if "exit=" in body:
                        code = re.search(r"exit=(-?\d+)", body)
                        if code and code.group(1) != "0":
                            errs.append(body[:200])
                    # v3.2: bukti file heredoc/redirect via helper sadar-cd
                    _scan_cmd_files(body, files)
            task.messages.append({"role": "user", "content": "<tool_results>\n" + out + "\n</tool_results>"})
        else:
            # v3.0.1 safety-net: model claim selesai tanpa satu tool pun (free model
            # sering begitu) → 1x nudge format canonical, mirip loop utama v2.9.5.
            if not had and not nudged:
                nudged = True
                task.messages.append({"role": "user", "content": (
                    "Kamu belum memanggil tool apa pun tapi mengklaim sudah mengerjakan. "
                    "Panggil tool SEKARANG dengan format canonical persis "
                    "(invoke name antml:computer:execute_command + parameter command), "
                    "baru laporkan STATUS: success|partial|failed.")})
                continue
            break
    return {"reply": reply, "had_tools": had, "actions": actions,
            "files": files, "cmds": cmds, "err": errs}


# ── CRITIC ───────────────────────────────────────────────────────────
def critic(task):
    task.transition("VERIFYING")
    # bukti: hasil subtask + error tool + test. LLM menilai vs success_criteria.
    ev = []
    for sid, r in task.subtask_results.items():
        ev.append(f"{sid}: status={r['status']} files={r['files_changed']} "
                  f"errors={r['errors']}\n"
                  f"  actions (bukti mentah):\n    " +
                  "\n    ".join(a.replace("\n", " ⏎ ") for a in r.get("actions", [])[:10]) +
                  f"\n  tail reply: {r.get('reply_tail','')}")
    ev = "\n".join(ev)[-4000:]
    verdict = _ask_json(task,
        "Kamu Critic yang skeptis. JANGAN percaya klaim executor — nilai dari BUKTI "
        "(file, exit code, error, test). Balas HANYA JSON: "
        '{"status":"pass|fail","requirements_met":[str],"requirements_failed":[str],'
        '"bugs":[str],"recommendation":"complete|repair|retry"}. '
        "Kalau bukti tidak cukup untuk klaim sukses → fail.",
        f"GOAL: {task.plan.get('goal', task.goal)}\n"
        f"KRITERIA SUKSES: {json.dumps(task.plan.get('success_criteria', []), ensure_ascii=False)}\n"
        f"BUKTI EKSEKUSI:\n{ev}")
    verdict.setdefault("status", "fail")
    verdict.setdefault("recommendation", "repair")
    task.critic = verdict
    _log("CRITIC", f"status={verdict['status']} rec={verdict.get('recommendation')} "
                   f"failed={len(verdict.get('requirements_failed', []))}", task.id)
    return verdict


# ── DEBUGGER / REPAIR ────────────────────────────────────────────────
def debugger(task):
    task.transition("DEBUGGING")
    fails = "; ".join(task.critic.get("requirements_failed", []) +
                      task.critic.get("bugs", []))[:800]
    ev = "\n".join(f"{s}: {r['errors']}" for s, r in task.subtask_results.items())[-1500:]
    d = _ask_json(task,
        "Kamu Debugger. Analisis root cause (BUKAN asal fix). Balas HANYA JSON: "
        '{"error":str,"root_cause":str,"component":str,"fix_steps":[str],"confidence":0-1}',
        f"KRITIK: {fails}\nBUKTI ERROR:\n{ev}")
    d["confidence"] = float(d.get("confidence", 0) or 0)
    task.debug_log.append(d)
    _log("DEBUGGER", f"root_cause={d.get('root_cause', '?')[:90]} conf={d['confidence']}", task.id)
    return d


def repair(task):
    task.transition("REPAIRING")
    task.repair_count += 1
    _log("REPAIR", f"attempt={task.repair_count}", task.id)
    d = task.debug_log[-1]
    fix_prompt = ("REPARASI (percobaan " + str(task.repair_count) + "): perbaiki masalah ini:\n"
                  f"Root cause: {d.get('root_cause')}\nLangkah: {d.get('fix_steps')}\n"
                  "Kerjakan pakai tool, lalu laporkan STATUS: success|partial|failed + bukti.")
    task.messages.append({"role": "user", "content": fix_prompt})
    used = {"n": 0}
    res = _run_tools(task, used)
    task.tool_calls += used["n"]
    _unblock_ready(task)  # v3.2: dependent BLOCKED boleh hidup lagi setelah fix
    # gabungkan bukti repair ke subtask terdampak supaya Critic menilai BUKTI BARU,
    # bukan klaim lama yang sudah basi
    for sid, r in task.subtask_results.items():
        if r["status"] != "success":
            r["status"] = "partial"
            r["actions"] = (r.get("actions", []) + res.get("actions", []))[-20:]
            r["files_changed"] = list({*r.get("files_changed", []), *res.get("files", [])})
            r["errors"] = [e for e in res.get("err", []) if e][:8] or r.get("errors", [])
            r["reply_tail"] = res.get("reply", "")[-400:]
            break
    return res


def _deps(st):
    return st.get("depends_on") or st.get("dependencies") or []


def graph_validate(subtasks):
    """FEATURE 5/13: DAG check eksplisit — cycle A→B→A DITOLAK, dep tak dikenal
    dilaporkan. Return (valid, topo_order, cycle, unknown_deps)."""
    ids = [st["id"] for st in subtasks]
    idset = set(ids)
    edges = {i: [d for d in _deps(next(s for s in subtasks if s["id"] == i)) if d in idset]
             for i in ids}
    unknown = sorted({d for st in subtasks for d in _deps(st) if d not in idset})
    indeg = {i: len(edges[i]) for i in ids}
    rev = {i: [] for i in ids}
    for i, ds in edges.items():
        for d in ds:
            rev[d].append(i)
    q = [i for i in ids if indeg[i] == 0]
    order = []
    while q:
        n = q.pop(0)
        order.append(n)
        for m in rev[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    cycle = sorted(idset - set(order)) if len(order) != len(ids) else None
    return {"valid": not cycle, "order": order, "cycle": cycle, "unknown_deps": unknown}


# ── v3.2 SCHEDULER / AGENT POOL / MERGER ───────────────────────────────
# Prinsip: paralel HANYA kalau DAG + klasifikasi resource membuktikannya aman.
# Semua state paralel di-guard task.lock; tidak pernah mutate task.messages dari worker.

_WRITE_RE = re.compile(r"write_file|edit_file", re.I)
_DESTRUCTIVE_RE = re.compile(r"\brm\b|\bmv\b|rmdir|unlink", re.I)
_NETWORK_RE = re.compile(r"http_request|download_file|web_search|browse|curl|wget", re.I)
_TEST_RE = re.compile(r"\btest|pytest|unittest|npm test|run_code", re.I)
_PATH_RE = re.compile(r"([\w~/][\w./-]*\.\w{1,4})\b")


def classify_subtask(st):
    """FEATURE 9: klasifikasi jenis aksi subtask dari teks deskripsi/tool/skill.
    READ_ONLY | WRITE | NETWORK | DESTRUCTIVE | TEST | MIXED. Uncertain → MIXED
    (konservatif: MIXED tidak pernah paralel dgn writer lain)."""
    hay = " ".join([st.get("description", "")] + (st.get("required_tools") or [])
                   + (st.get("required_skills") or [])).lower()
    if _DESTRUCTIVE_RE.search(hay):
        return "DESTRUCTIVE"
    if _WRITE_RE.search(hay) or re.search(r"\bbuat file|tulis file|buat file|ubah|edit|implement", hay):
        if _TEST_RE.search(hay):
            return "MIXED"
        return "WRITE"
    if _TEST_RE.search(hay):
        return "TEST"
    if _NETWORK_RE.search(hay):
        return "NETWORK"
    if re.search(r"riset|research|baca|read|analisis|cari|docs", hay):
        return "READ_ONLY"
    return "MIXED"


def predict_writes(st):
    """FEATURE 8: prediksi file yang DITULIS subtask (dari teks goal).
    Conservative: yang ke-scan regex + terbaca eksplisit. Tidak memprediksi =
    dianggap konflik dgn semua writer (serial) utk WRITE/DESTRUCTIVE."""
    txt = st.get("description", "")
    return {m.group(1) for m in _PATH_RE.finditer(txt) if not m.group(1).startswith(("/proc", "/sys", "/dev"))}


_CONFLICT = {
    # (a,b) → boleh paralel?
    ("READ_ONLY", "READ_ONLY"): True, ("READ_ONLY", "TEST"): True,
    ("TEST", "READ_ONLY"): True, ("NETWORK", "READ_ONLY"): True,
    ("READ_ONLY", "NETWORK"): True, ("NETWORK", "TEST"): True,
    ("TEST", "NETWORK"): True, ("TEST", "TEST"): True,
    ("NETWORK", "NETWORK"): True,
}


def safe_parallel(a, b, fa, fb):
    """FEATURE 8/9: dua subtask boleh concurrent? Rules:
    - writer (WRITE/DESTRUCTIVE/MIXED) tidak pernah paralel dgn writer lain,
      KECUALI file tertulis disjoint TERBUKTI (keduanya prediksi non-kosong)
    - writer paralel dgn reader: hanya jika file prediksi reader tidak bersinggungan
      → conservative: TIDAK boleh kecuali reader READ_ONLY murni tanpa path bentrok."""
    ta, tb = a["type"], b["type"]
    wa = ta in ("WRITE", "DESTRUCTIVE", "MIXED")
    wb = tb in ("WRITE", "DESTRUCTIVE", "MIXED")
    if wa and wb:
        if fa and fb and not (fa & fb):
            return True   # disjoint write-sets terbukti
        return False
    if wa and tb == "READ_ONLY" and fa:
        return not (fa & fb) if fb is not None else False
    if wb and ta == "READ_ONLY" and fb:
        return not (fa & fb)
    key = (ta, tb)
    return _CONFLICT.get(key, False)


def match_capability(task, st):
    """FEATURE 6: pilih agen utk subtask via registry ASLI (health+rank bukti).
    Return dict {agent, skills, health} — capability tak tersedia → None (caller
    route ke riset/builder, bukan paksa jalan)."""
    caps = st.get("required_skills") or []
    if not caps:
        # tebak agent dari tipe aksi (bukan registry)
        t = st["type"]
        agent = {"WRITE": "coder", "TEST": "tester", "NETWORK": "browser",
                 "READ_ONLY": "researcher", "DESTRUCTIVE": "coder", "MIXED": "coder"}.get(t, "coder")
        return {"agent": agent, "skills": [], "health": None}
    rep = task.skill_report or {}
    pool = list(rep.get("available_skills", [])) + \
        [x["skill"] for x in rep.get("low_confidence", [])] + \
        [x["skill"] for x in rep.get("outdated_skills", [])]
    best = None
    for cap in caps:
        ranked = registry.rank(cap, pool)
        if not ranked:
            continue
        cand = ranked[0]
        if cand["health"] in ("BROKEN", "STALE"):
            continue
        if best is None or cand["score"] > best["score"]:
            best = cand
    agent = {"research": "researcher", "test": "tester", "scrap": "browser",
             "build": "coder", "web": "browser"}.get((caps[0] or "").split("/")[0] if caps else "", "coder")
    return {"agent": agent, "skills": caps, "health": best["health"] if best else None,
            "score": best["score"] if best else 0.0}


class Scheduler:
    """FEATURE 1/2/3/4/11/12/13: dependency-aware, bounded, conflict-safe."""

    def __init__(self, task):
        self.t = task
        self.pending = {st["id"]: st for st in task.plan["subtasks"]}
        self.completed, self.failed, self.blocked, self.cancelled = set(), set(), set(), set()
        self.running = {}          # id → future
        self.files_locked = {}     # path → subtask id (writer aktif)

    def _state(self, sid):
        with self.t.lock:
            return self.t.sub_states.get(sid)

    def _set(self, sid, st):
        with self.t.lock:
            self.t.sub_states[sid] = st

    def budget_exhausted(self):
        t = self.t
        with t.lock:
            calls = getattr(t, "agent_calls", 0) + t.tool_calls
            dur = t.elapsed()
        if t.cancelled:
            return "CANCELLED"
        if dur > t.limits["timeout"]:
            return "RESOURCE_LIMIT_REACHED:timeout"
        if calls >= t.limits["max_total_agent_calls"]:
            return "RESOURCE_LIMIT_REACHED:max_total_agent_calls"
        if t.tool_calls >= t.limits["max_tool_calls"]:
            return "RESOURCE_LIMIT_REACHED:max_tool_calls"
        return None

    def ready_nodes(self):
        """NODE = deps COMPLETED, classify-safe (scheduler yang atur konflik).
        Efek samping terkontrol: dep FAILED/BLOCKED/CANCELLED → node jadi BLOCKED
        (FEATURE 12: gagal propagate ke dependent, branch lain tetap valid)."""
        out, blocked_dead = [], []
        for sid in self.pending:
            if self._state(sid) in (None, "PENDING"):
                deps = _deps(self.pending[sid])
                if all(self._state(d) == "COMPLETED" for d in deps):
                    out.append(self.pending[sid])
                elif any(self._state(d) in ("FAILED", "BLOCKED", "CANCELLED") for d in deps):
                    # FEATURE 12: dep mati → propagate BLOCKED (jgn tunggu selamanya)
                    blocked_dead.append(self.pending[sid])
        for st in blocked_dead:
            sid = st["id"]
            bad = [d for d in _deps(st) if d in self.failed or d in self.blocked or d in self.cancelled]
            self._set(sid, "BLOCKED")
            self.t.subtask_results[sid] = {"status": "failed", "actions": [],
                "files_changed": [], "commands_executed": [],
                "errors": [f"dependency {bad} tidak COMPLETED (BLOCKED)"]}
            self.blocked.add(sid)
            self.pending.pop(sid, None)
            _log("EXECUTOR", f"subtask={sid} BLOCKED dep={bad}", self.t.id)
        return out

    def _conflicts_free(self, cand, chosen):
        """cand boleh gabung dgn chosen (writer aktif) & antar-chosen baru?"""
        for other_id, other in chosen.items():
            if not safe_parallel(cand, other,
                                 predict_writes(cand), predict_writes(other)):
                return False
        for other in self.running.values():
            if other.running_writer:
                if not safe_parallel(cand, other.st,
                                     predict_writes(cand), other.writes):
                    return False
        return True

    def cancel_all(self, reason):
        """FEATURE 13: cancellation bounded — future aktif dibatalkan."""
        self.t.cancelled = True
        n = 0
        for sid, w in list(self.running.items()):
            if w.future.cancel():
                self._set(sid, "CANCELLED")
                self.cancelled.add(sid)
                self.pending.pop(sid, None)
                n += 1
            # yang sudah RUNNING: tidak bisa paksa bunuh thread (bounded: worker
            # cek budget_exhausted tiap round → RESOURCE_LIMIT_REACHED keluar sendiri)
            else:
                w.request_cancel = True
        for sid in list(self.pending):
            if self._state(sid) in (None, "PENDING"):
                self._set(sid, "CANCELLED")
                self.cancelled.add(sid)
                self.pending.pop(sid, None)
                n += 1
        _log("SCHEDULER", f"CANCEL reason={reason} cancelled={n}", self.t.id)
        return reason


class _Worker:
    """Satu unit kerja paralel: subtask + client privat (hindari race last_usage)."""
    def __init__(self, sid, st, client):
        self.sid, self.st, self.client = sid, st, client
        self.future = None
        self.request_cancel = False
        self.running_writer = st["type"] in ("WRITE", "DESTRUCTIVE", "MIXED")
        self.writes = predict_writes(st)


def run_subtask(task, st, client, counter):
    """Dipanggil lewat _worker_fn/_run_serial_one; utk testability, kalau
    `executor` di-monkeypatch (bukan fungsi asli), jalur paralel pakai itu."""
    """FEATURE 7: konteks TERISOLASI per subtask — pesan khusus subtask,
    relevant memory (bukan seluruh history), tanpa mutate task.messages."""
    mem = experience.recall(st["description"], top_k=1)
    mem_block = ""
    if mem["similar_tasks"]:
        m = mem["similar_tasks"][0]
        mem_block = (f"\nPengalaman relevan (bukti, verifikasi lagi): {m['approach'][:3]} "
                     f"dengan skills {m['skills_used'][:3]}")
    prompt = (f"SUBTASK ({st['id']}): {st['description']}\n"
              f"Dari goal: {task.plan.get('goal', task.goal)[:120]}\n"
              f"Tipe: {st['type']} | Agent: {st.get('agent', 'coder')} | "
              f"Skill: {', '.join(st.get('required_skills', [])) or '-'}"
              + mem_block +
              "\nKerjakan SEKARANG pakai tool. Akhiri dengan STATUS: success|partial|failed "
              "dan bukti nyata (file, exit code, test).")
    msgs = [{"role": "system", "content": soul.build_system_prompt()},
            {"role": "user", "content": prompt}]
    return _run_tools_in(task, msgs, client, counter)


def _run_tools_in(task, msgs, client, counter):
    """_run_tools tapi dgn message-list & client milik sendiri (thread-safe)."""
    model = task.model or config.DEFAULT_MODEL
    max_rounds = max(2, min(task.limits["max_agent_steps"], 8))
    reply, actions, files, cmds, errs = "", [], [], [], []
    had = False
    nudged = False
    for _ in range(max_rounds):
        if task.cancelled or counter["n"] >= task.limits["max_tool_calls"]:
            errs.append("RESOURCE_LIMIT_REACHED:cancelled_or_tools")
            break
        r = client.chat_failover(model, msgs, config.FAILOVER_CHAIN,
                                 timeout=min(config.HTTP_TIMEOUT, 120),
                                 max_tokens=task.limits.get("sub_agent_max_tokens", 1500))
        reply = r[0] if isinstance(r, tuple) else r
        if reply is None:
            errs.append("all models failed")
            break
        msgs.append({"role": "assistant", "content": reply})
        out = tags.dispatch(reply, config.SELF_PATH)
        counter["n"] += 1 if out else 0
        if out:
            had = True
            for mm in re.finditer(r"\[(\w+)\]\n([\s\S]*?)(?=\n\n\[|$)", out):
                tool_name, body = mm.group(1), mm.group(2)
                actions.append(f"{tool_name}: {body[:250]}")
                if tool_name in ("write_file", "edit_file"):
                    mp = re.search(r"wrote to\s+(\S+)", body)
                    files.append(mp.group(1) if mp else body[:120])
                if tool_name == "execute_command":
                    cmds.append(body[:120])
                    if "exit=" in body:
                        code = re.search(r"exit=(-?\d+)", body)
                        if code and code.group(1) != "0":
                            errs.append(body[:200])
                    _scan_cmd_files(body, files)
            msgs.append({"role": "user", "content": "<tool_results>\n" + out + "\n</tool_results>"})
        else:
            if not had and not nudged:
                nudged = True
                msgs.append({"role": "user", "content": (
                    "Kamu belum memanggil tool apa pun tapi mengklaim sudah mengerjakan. "
                    "Panggil tool SEKARANG pakai format canonical "
                    "(invoke name antml:computer:execute_command + parameter command), "
                    "baru laporkan STATUS: success|partial|failed.")})
                continue
            break
    # v3.2-fix: STATUS marker eksplisit menang; kalau absen, pakai semantik v3.0
    # (tool kepanggil + tanpa error = success). Free/weak model sering lupa
    # menulis STATUS; dulu default "partial" → semua subtask gagal, repair loop
    # meledak tanpa sebab nyata.
    ms = re.search(r"STATUS\s*[:=]\s*(success|partial|failed)", reply or "", re.I)
    if ms:
        st = ms.group(1).lower()
    elif had and not errs:
        st = "success"
    elif had:
        st = "partial"
    else:
        st = "failed"
    return {"status": st, "actions": actions[:20], "files_changed": files[:20],
            "commands_executed": cmds[:20], "tests": [], "errors": errs[:8],
            "reply_tail": (reply or "")[-400:]}


_executor_orig = executor


def merge_results(task):
    """FEATURE 10: Result Merger — gabung, tapi TIDAK memutuskan sukses.
    Hanya Critic yang boleh."""
    with task.lock:
        subs = [{"id": sid, "status": r.get("status"), "errors": r.get("errors", [])[:3],
                 "files": r.get("files_changed", [])[:5]}
                for sid, r in task.subtask_results.items()]
        arts = sorted({f for r in task.subtask_results.values() for f in r.get("files_changed", [])})
        errs = [f"{sid}:{e}" for sid, r in task.subtask_results.items() for e in r.get("errors", [])]
        warn = [f"subtask {sid} {st}" for sid, st in task.sub_states.items()
                if st in ("FAILED", "BLOCKED", "CANCELLED")]
    task.merged = {"task_id": task.id, "subtasks": subs, "artifacts": arts,
                   "errors": errs[:10], "warnings": warn[:10]}
    return task.merged


def _execute_serial(task, byid):
    """Jalur v3.1.2 UTUH utk max_concurrent=1 / single subtask (regression-safe)."""
    for sid in task.graph["order"]:
        st = byid[sid]
        bad_dep = [d for d in _deps(st)
                   if task.sub_states.get(d) not in (None, "COMPLETED")]
        if bad_dep:
            task.sub_states[sid] = "BLOCKED"
            task.subtask_results[sid] = {"status": "failed", "actions": [],
                "files_changed": [], "commands_executed": [],
                "errors": [f"dependency {bad_dep} belum/tidak COMPLETED (BLOCKED)"]}
            _log("EXECUTOR", f"subtask={sid} BLOCKED dep={bad_dep}", task.id)
            continue
        task.sub_states[sid] = "READY"
        task.sub_states[sid] = "RUNNING"
        try:
            res = executor(task, st)
        except Exception as e:
            # v3.2-fix: exception executor → node FAILED terisolasi, state
            # terminal (bukan RUNNING yatim), sisa subtask tetap diproses.
            _log("EXECUTOR", f"subtask={sid} ERROR {type(e).__name__}: "
                 f"{str(e)[:120]}", task.id)
            res = {"status": "failed", "actions": [], "files_changed": [],
                   "commands_executed": [], "errors": [f"{type(e).__name__}: {e}"],
                   "tests": [], "reply_tail": ""}
        task.subtask_results[sid] = res
        task.sub_states[sid] = "COMPLETED" if res["status"] == "success" else "FAILED"
        _log("EXECUTOR", f"subtask={sid} {task.sub_states[sid]}", task.id)


def _ready_simple(sch):
    return [st for st in sch.pending.values()
            if all(d in sch.completed for d in _deps(st))]


def _wave_safe(cand, chosen, sch, task):
    fc = predict_writes(cand)
    for other in chosen.values():
        if not safe_parallel(cand, other, fc, predict_writes(other)):
            return False
    for w in sch.running.values():
        if w.running_writer or cand["type"] in ("WRITE", "DESTRUCTIVE", "MIXED"):
            if not safe_parallel(cand, w.st, fc, w.writes):
                return False
    return True


def _thread_client():
    """FEATURE 5: agen ringan = client privat per thread (hindari race
    last_usage/last_finish_reason) — TANPA proses baru."""
    try:
        return client_mod.LClient.for_provider(config.ACTIVE_PROVIDER)
    except Exception:
        return client_mod.LClient()


def _worker_fn(task, w):
    counter = {"n": 0}
    if executor is not _executor_orig:      # di-monkeypatch (deterministic test)
        res = executor(task, w.st)
    else:
        res = run_subtask(task, w.st, w.client, counter)
    with task.lock:
        task.tool_calls += counter["n"]
        task.agent_calls = getattr(task, "agent_calls", 0) + 1
    return res


def _run_serial_one(task, st):
    counter = {"n": 0}
    try:
        res = executor(task, st) if executor is not _executor_orig \
            else run_subtask(task, st, _thread_client(), counter)
    except Exception as e:
        # v3.2-fix: jangan biarkan exception membunuh seluruh run
        _log("AGENT", f"subtask={st.get('id')} ERROR {type(e).__name__}: "
             f"{str(e)[:120]}", task.id)
        return {"status": "failed", "actions": [], "files_changed": [],
                "commands_executed": [], "errors": [f"{type(e).__name__}: {e}"],
                "tests": [], "reply_tail": ""}
    with task.lock:
        task.tool_calls += counter["n"]
        task.agent_calls = getattr(task, "agent_calls", 0) + 1
    return res


def _finish_node(task, sch, sid, res):
    sch.running.pop(sid, None)
    sch.pending.pop(sid, None)   # v3.2-fix: tanpa ini node selesai dihitung ulang → CANCELLED palsu
    status = res.get("status", "failed")
    if status != "success":
        sch.failed.add(sid)
        task.sub_states[sid] = "FAILED"
    else:
        sch.completed.add(sid)
        task.sub_states[sid] = "COMPLETED"
    task.subtask_results[sid] = res
    _log("AGENT", f"subtask={sid} {task.sub_states[sid]} "
         f"files={len(res.get('files_changed', []))}", task.id)


def _execute_parallel(task, byid):
    """FEATURE 1/2/3/4/11/12/15/17: wave-scheduler bounded + conflict-safe."""
    sch = Scheduler(task)
    maxc = task.limits["max_concurrent_agents"]
    task.agent_calls = getattr(task, "agent_calls", 0)   # JANGAN reset (budget carry-over)
    pool = ThreadPoolExecutor(max_workers=maxc)
    try:
        while sch.pending or sch.running:
            reason = sch.budget_exhausted()
            if reason:
                sch.cancel_all(reason)
                task.error = reason
                break
            ready = sch.ready_nodes()
            chosen = {}
            for cand in ready:
                if len(chosen) + len(sch.running) >= maxc:
                    break
                if _wave_safe(cand, chosen, sch, task):
                    chosen[cand["id"]] = cand
                else:
                    # di-skip BUKAN karena penuh → konflik resource/artefak
                    task.parallel_stats["conflicts"] += 1
                    _log("SCHEDULER", f"conflict: {cand['id']} ditunda "
                         f"(writer bentrok)", task.id)
            for sid, st in chosen.items():
                w = _Worker(sid, st, _thread_client())
                w.future = pool.submit(_worker_fn, task, w)
                sch.running[sid] = w
                task.sub_states[sid] = "RUNNING"
                with task.lock:
                    task.parallel_stats["parallel"] = True
                    task.parallel_stats["max_concurrency"] = max(
                        task.parallel_stats["max_concurrency"], len(sch.running))
                if len(sch.running) > 1:
                    task.parallel_stats["parallel_tasks"] += len(sch.running)
                _log("AGENT", f"subtask={sid} agent={st.get('agent')} RUNNING "
                     f"conc={len(sch.running)}/{maxc}", task.id)
            if not sch.running:
                if chosen:
                    continue  # baru saja submit; loop lagi
                if ready:
                    # ready tapi konflik satu-satu → serialize deterministik 1
                    st = ready[0]
                    _log("SCHEDULER", f"serialize={st['id']} reason=write_conflict", task.id)
                    task.sub_states[st["id"]] = "RUNNING"
                    res = _run_serial_one(task, st)
                    _finish_node(task, sch, st["id"], res)
                    continue
                dead = False
                for sid in list(sch.pending):
                    deps = _deps(sch.pending[sid])
                    bad = [d for d in deps if d in sch.failed or d in sch.blocked or d in sch.cancelled]
                    if bad:
                        task.sub_states[sid] = "BLOCKED"
                        task.subtask_results[sid] = {"status": "failed", "actions": [],
                            "files_changed": [], "commands_executed": [],
                            "errors": [f"dependency {bad} tidak COMPLETED (BLOCKED)"]}
                        sch.blocked.add(sid)
                        sch.pending.pop(sid)
                        _log("EXECUTOR", f"subtask={sid} BLOCKED dep={bad}", task.id)
                        dead = True
                if not dead:
                    for sid in list(sch.pending):
                        task.sub_states[sid] = "CANCELLED"
                        sch.cancelled.add(sid)
                        sch.pending.pop(sid)
                    task.parallel_stats["cancellations"] += len(sch.cancelled)
                    break
                continue
            done = []
            while not done:
                for sid, w in list(sch.running.items()):
                    if w.future.done():
                        try:
                            done.append((sid, w.future.result()))
                        except Exception as e:
                            # v3.2-fix: worker melempar (mis. reply=None) → jangan
                            # biarkan node nyangkut RUNNING & loop mati. Tandai
                            # FAILED terisolasi; branch lain tetap lanjut.
                            _log("AGENT", f"subtask={sid} ERROR {type(e).__name__}: "
                                 f"{str(e)[:120]}", task.id)
                            done.append((sid, {"status": "failed", "actions": [],
                                               "files_changed": [], "commands_executed": [],
                                               "errors": [f"{type(e).__name__}: {e}"],
                                               "tests": [], "reply_tail": ""}))
                if not done:
                    time.sleep(0.05)
            for sid, res in done:
                _finish_node(task, sch, sid, res)
    finally:
        pool.shutdown(wait=False)


def _unblock_ready(task):
    """FEATURE 11/15: dependent BLOCKED yg semua dep-nya kini COMPLETED → jalankan."""
    for st in task.plan.get("subtasks", []):
        sid = st["id"]
        if task.sub_states.get(sid) != "BLOCKED":
            continue
        deps = _deps(st)
        if any(task.sub_states.get(d) in ("FAILED", "CANCELLED") for d in deps):
            continue   # dep mati permanen → tetap BLOCKED (bukan READY)
        if all(task.sub_states.get(d) == "COMPLETED" for d in deps):
            st["type"] = st.get("type") or classify_subtask(st)
            task.sub_states[sid] = "RUNNING"
            _log("EXECUTOR", f"subtask={sid} UNBLOCKED→RUNNING", task.id)
            res = executor(task, st)
            task.subtask_results[sid] = res
            task.sub_states[sid] = "COMPLETED" if res["status"] == "success" else "FAILED"
            _log("EXECUTOR", f"subtask={sid} {task.sub_states[sid]} (unblocked)", task.id)


def _retry_failed(task):
    """FEATURE 15: retry paralel utk branch gagal non-conflict; serialize jika konflik."""
    byid = {st["id"]: st for st in task.plan["subtasks"]}
    for sid in list(task.sub_states):
        if task.sub_states[sid] == "FAILED" and "type" not in byid.get(sid, {}):
            byid[sid]["type"] = classify_subtask(byid[sid])
    failed = [sid for sid in task.graph["order"]
              if task.subtask_results.get(sid, {}).get("status") != "success"
              and task.sub_states.get(sid) not in ("BLOCKED", "CANCELLED")]
    if not failed:
        _unblock_ready(task)
        return
    maxc = task.limits["max_concurrent_agents"]
    waves = []
    cur = {}
    for sid in failed:
        st = byid[sid]
        if cur and all(safe_parallel(st, o, predict_writes(st), predict_writes(o))
                       for o in cur.values()) and len(cur) < maxc:
            cur[sid] = st
        else:
            if cur:
                waves.append(cur)
                task.parallel_stats["conflicts"] += 1
            cur = {sid: st}
    if cur:
        waves.append(cur)
    for wave in waves:
        if len(wave) == 1 or maxc <= 1:
            for sid in wave:
                task.sub_states[sid] = "RUNNING"
                task.subtask_results[sid] = executor(task, wave[sid])
                task.sub_states[sid] = ("COMPLETED" if
                    task.subtask_results[sid]["status"] == "success" else "FAILED")
                _log("AGENT", f"subtask={sid} retry {task.sub_states[sid]}", task.id)
        else:
            pool = ThreadPoolExecutor(max_workers=min(len(wave), maxc))
            futs = {}
            for sid in wave:
                task.sub_states[sid] = "RUNNING"
                futs[pool.submit(_run_serial_one, task, wave[sid])] = sid
            _log("AGENT", f"retry-parallel n={len(futs)}", task.id)
            for f, sid in futs.items():
                res = f.result()
                task.subtask_results[sid] = res
                task.sub_states[sid] = "COMPLETED" if res["status"] == "success" else "FAILED"
                _log("AGENT", f"subtask={sid} retry {task.sub_states[sid]}", task.id)
            pool.shutdown(wait=True)
    _unblock_ready(task)


def redecompose_independent(goal, subs, max_subtasks=5):
    """FEATURE 1 (deterministic): bila planner cuma kasih 1 subtask padahal goal
    menyebut bagian independen eksplisit ((1)(2)(3)/'paralel'/'independen'),
    pecah jadi N subtask + 1 subtask integrasi ber-dependency. Struktur, bukan
    tebakan LLM. Return list subtasks baru (atau sama kalau tidak applicable)."""
    g = (goal or "")
    gl = g.lower()
    if len(subs) > 1 or not re.search(r"\(\s*1\s*\)|independen|paralel|bebas", gl):
        return subs
    items = re.findall(r"\(\s*\d\s*\)\s*(.+?)(?=\s*\(\s*\d\s*\)|\.\s+[A-Z]|$)", g)
    if len(items) < 2:
        # split numeric-list style: "1. xxx 2. yyy"
        items = re.findall(r"\d+[.)\-]\s+(.{8,}?)(?=\s+\d+[.)\-]|$)", g)
    if len(items) < 2:
        return subs
    items = [re.sub(r"\s+", " ", it).strip(" ,.;:")[:160] for it in items][:max_subtasks - 1]
    news = [{"id": f"i{n+1}", "description": it, "required_skills": [],
             "required_tools": [], "depends_on": []} for n, it in enumerate(items)]
    tail = re.search(r"(setelah (?:ketiganya|semuanya|keduanya) selesai[^.]*\.?|integrasi[^.]*\.?)", gl)
    if tail:
        news.append({"id": "integ", "description": tail.group(0)[:200],
                     "required_skills": [], "required_tools": [],
                     "depends_on": [x["id"] for x in news]})
    _log("SCHEDULER", f"re-decompose {len(subs)}→{len(news)} (independent branches)", "preview")
    return news


# ── ROUTER / RUN ─────────────────────────────────────────────────────
def run(task):
    """Loop utama delegasi. Orchestrator TIDAK mengerjakan sendiri."""
    # v3.2: kunci scope eksekusi ke direktori task (bila goal menyebut path
    # workspace/<dir>) — cegah agent/repair menyentuh project lain.
    try:
        import re as _re
        _m = _re.search(r"workspace/([A-Za-z0-9_.-]+)", task.goal or "")
        config.TASK_DIR = os.path.join(config.WORKSPACE, _m.group(1)) if _m else None
    except Exception:
        config.TASK_DIR = None
    try:
        planner(task)
        skill_analyst(task)
        adaptive_strategy(task)
        if task.skill_report["action"] in ("RESEARCH_AND_BUILD_SKILLS", "UPDATE_SKILLS"):
            researcher(task)
            build_missing_skills(task)
        # FEATURE 5: dependency graph — validasi dulu, tolak cycle, baru eksekusi topo
        plan_subs = task.plan.get("subtasks", [])
        subs = plan_subs
        task.graph = graph_validate(subs)
        _log("DEPENDENCY", f"graph_valid={task.graph['valid']} "
             f"order={'>'.join(task.graph['order']) if task.graph['valid'] else task.graph['cycle']}",
             task.id)
        if not task.graph["valid"]:
            task.transition("EXECUTING")  # state legal, tapi langsung gagal (bounded)
            task.transition("FAILED")
            task.error = f"dependency cycle: {task.graph['cycle']}"
            _learn(task, ok=False)
            _history(task)
            return task
        # v3.2: LLM planner sering menggabung bagian independen jadi 1 mega-subtask
        # → re-dekomposisi DETERMINISTIK berdasar struktur goal (bukan mood model).
        subs = redecompose_independent(task.goal, subs, task.limits.get("max_subtasks", 5))
        task.plan["subtasks"] = subs
        task.graph = graph_validate(subs)
        if not task.graph["valid"]:   # re-decompose bikin cycle? (shouldn't) fallback
            task.plan["subtasks"] = subs = plan_subs
            task.graph = graph_validate(subs)
        _log("SCHEDULER", f"subtasks_final={len(subs)} "
             f"independent={sum(1 for x in subs if not _deps(x))}", task.id)
        for sid in task.graph["order"]:
            task.sub_states[sid] = "PENDING"
        byid = {st["id"]: st for st in subs}
        for st in subs:
            st["type"] = classify_subtask(st)
            st.update(match_capability(task, st))
        task.transition("EXECUTING")
        # parallel scheduler dipakai bila maxc>1 dan ada ≥2 node ATAU budget perlu ditegakkan
        if task.limits.get("max_concurrent_agents", 1) <= 1 or (len(subs) <= 1 and task.elapsed() < task.limits.get("timeout", 1800)):
            _execute_serial(task, byid)
        else:
            _execute_parallel(task, byid)
        merge_results(task)
        _log("MERGER", f"branches={len(task.subtask_results)} "
             f"conflicts={task.parallel_stats['conflicts']} "
             f"max_conc={task.parallel_stats['max_concurrency']}", task.id)
        execution_started = time.time()
        task.planning_metrics["execution_latency"] = round(execution_started - task.t0, 4)
        while True:
            c = critic(task)
            if c["status"] == "pass":
                task.final_solution = "; ".join(
                    f"{sid}: {r['status']} files={r['files_changed'][:3]}"
                    for sid, r in task.subtask_results.items())[:600]
                task.transition("COMPLETED")
                _learn(task, ok=True)
                break
            rec = c.get("recommendation", "repair")
            if (rec == "retry" and task.repair_count < task.limits["max_retries"]
                    and task.repair_count < task.limits["max_repair_attempts"]):
                # retry = eksekusi ulang subtask yang gagal
                _retry_failed(task)
                task.repair_count += 1
                continue
            if (rec == "repair" and task.repair_count < task.limits["max_repair_attempts"]
                    and task.elapsed() < task.limits["timeout"]):
                debugger(task)
                repair(task)
                continue
            # v3.3: classify before a bounded strategy switch; never oscillate.
            task.strategy_failure = strategy_mod.classify_failure(task, c)
            if task.strategy:
                strategy_mod.REGISTRY.record_outcome(
                    task.strategy.id, False, duration=task.elapsed(),
                    cost=getattr(task, "agent_calls", 0) + task.tool_calls,
                    repaired=task.repair_count > 0,
                    evidence=[{"type": "task_id", "id": task.id,
                               "detail": task.strategy_failure["classification"]}])
            if task.strategy and _switch_strategy(task):
                continue
            task.transition("FAILED")
            task.error = "kriteria tidak terpenuhi setelah retry/repair habis"
            _learn(task, ok=False)
            break
    except Exception as ex:
        import traceback
        task.transition("FAILED")
        task.error = str(ex)[:200]
        _log("CORE", f"EXC {ex}\n{traceback.format_exc()[-800:]}", task.id)
    finally:
        task.planning_metrics["total_latency"] = round(task.elapsed(), 4)
        config.TASK_DIR = None   # jangan bocor ke task berikutnya
    _history(task)
    return task


def _learn(task, ok):
    """Learning signal terkontrol → registry metrics. Tidak ada self-modif bebas."""
    if not task.skill_report:
        return
    registry.record_use(task.skill_report.get("available_skills", []), success=ok)
    if task.strategy:
        strategy_mod.REGISTRY.record_outcome(
            task.strategy.id, ok, duration=task.elapsed(),
            cost=getattr(task, "agent_calls", 0) + task.tool_calls,
            repaired=task.repair_count > 0,
            evidence=([{"type": "task_id", "id": task.id,
                        "detail": "completed" if ok else "failed"}]))
    try:
        from core import learning
        learning.record_verdict("OK" if ok else "REVISE")
    except Exception:
        pass
    # FEATURE 12: memory feedback — hanya kalau task memang recall
    if task.recalled_ids:
        try:
            experience.feedback(task.id, "success" if ok else "failure",
                              memory_ids=task.recalled_ids)
            _log("MEMORY", f"feedback task={task.id} outcome={'success' if ok else 'failure'} "
                 f"on={len(task.recalled_ids)} memory", task.id)
        except Exception:
            pass
    # v3.5: feedback ke semantic memory (Phase 16) — kalau planner pakai memori semantic
    if getattr(task, "semantic_memories", None):
        try:
            import core.memory as semantic_mem
            used_ids = [m["id"] for m in task.semantic_memories]
            # BULK: feedback batch sekali tulis — feedback() per-id menulis ulang
            # memories.json tiap iterasi (80+ hit → 3s di Termux I/O). Sanity:
            # max 300 id, sisanya di-cap (performa > feedback granular per hit).
            semantic_mem.feedback_batch(used_ids[:300], "success" if ok else "failure")
            _log("MEMORY", f"v3.5 semantic feedback on={len(used_ids)} outcome={'success' if ok else 'failure'}", task.id)
        except Exception:
            pass


def _history(task):
    """v3.1: delegasi ke experience (Task Memory kaya, super-set entri v3.0)."""
    try:
        experience.save_task_memory(task)
    except Exception:
        pass
    # v3.5: ekstrak memori terstruktur (TASK/SOLUTION/LESSON) dari task selesai (Phase 3/11/12)
    try:
        import core.memory as semantic_mem
        extracted = semantic_mem.extract_from_task(task)
        if extracted:
            _log("MEMORY", f"v3.5 extracted {len(extracted)} structured memories", task.id)
            # v3.6: tautkan memori baru ke entity graph (Phase 12) — evidence = entity list memori
            from core import capture as graph_capture
            linked = sum(1 for mem in extracted if graph_capture.record_memory_link(mem).get("ok"))
            if linked:
                _log("GRAPH", f"v3.6 linked {linked} memories to entities", task.id)
    except Exception as ex:
        _log("MEMORY", f"v3.5 extract skipped: {ex}", task.id)
    # v3.6: bangun/update Knowledge Graph + World Model dari task nyata (Phase 24)
    try:
        from core import capture as graph_capture
        trace = graph_capture.record_task(task)
        task.graph_trace = trace
        _log("GRAPH", f"v3.6 recorded nodes={trace['nodes']} edges={trace['edges']} "
             f"conflicts={trace['conflicts']} dropped={trace['dropped']}", task.id)
    except Exception as ex:
        _log("GRAPH", f"v3.6 record skipped: {ex}", task.id)


def status(task):
    return task.to_dict()


# ── entry utk TUI (slash /task) ──────────────────────────────────────
def start(goal, client=None, model=None):
    t = Task(goal, client=client, model=model)
    _log("CORE", f"Task diterima: {goal[:90]}")
    return run(t)


# ── interface utk tag <task/> (loop utama) & /task TUI ───────────────
def cli_report(goal):
    """Panggilan dari dispatcher tag <task goal=.../> di dalam turn biasa."""
    t = start(goal)
    return report_text(t)


def report_text(t):
    lines = [f"TASK {t.id}  state={t.state}  steps={t.steps}  tools={t.tool_calls}  "
             f"repairs={t.repair_count}  {t.elapsed():.0f}s", f"Goal: {t.goal[:160]}"]
    if t.strategy:
        lines.append(f"Adaptive strategy: {t.strategy.id} ({t.strategy.execution_style}) "
                     f"confidence={t.strategy_confidence} switches={t.strategy_switches}")
        if t.strategy_candidates:
            lines.append("Candidates: " + ", ".join(s.id for s in t.strategy_candidates))
        if t.strategy_selection:
            lines.append("Strategy reasons: " + "; ".join(
                t.strategy_selection.get("reasoning", [])[:4]))
            lines.append("Strategy evidence: " + str(
                t.strategy_selection.get("evidence_level", "LOW")))
    if t.skill_gaps:
        lines.append("Skill gaps: " + "; ".join(
            f"{g.capability_required}→{g.recommended_action}" for g in t.skill_gaps[:5]))
    if t.skill_evolution:
        lines.append("Skill evolution: " + "; ".join(
            f"{e.get('capability', e.get('skill', '?'))}:{e.get('stage', e.get('result', '?'))}"
            for e in t.skill_evolution[-5:]))
    if t.planning_metrics:
        pm = t.planning_metrics
        lines.append("Adaptive metrics: candidates={0} selected={1} explored={2} "
                     "planning={3}s total={4}s".format(
                         pm.get("strategy_candidates_generated", 0),
                         pm.get("strategy_selected", 0),
                         pm.get("strategy_exploration", 0),
                         pm.get("planning_latency", 0), pm.get("total_latency", 0)))
    if t.plan:
        lines.append(f"Plan ({t.complexity}): " + "; ".join(
            f"{s['id']} {s['description'][:40]}" for s in t.plan.get("subtasks", [])))
    if t.skill_report:
        r = t.skill_report
        lines.append(f"Skills: +{len(r['available_skills'])} avail, "
                     f"-{len(r['missing_skills'])} missing, {len(r['outdated_skills'])} outdated → {r['action']}")
    for n in t.research_notes:
        lines.append(f"Research: {n['capability']} ({len(n.get('pages', []))} sumber)")
    for sid, r in t.subtask_results.items():
        lines.append(f"  {sid}: {r['status']} ({len(r['files_changed'])} file, {len(r['errors'])} err)")
    if t.recalled_ids:
        lines.append("Memory recall: " + ", ".join(
            f"{m['memory_id']} sim={m['similarity']} {m['result']}" for m in t.recalled[:3]))
    if t.parallel_stats.get("parallel"):
        ps = t.parallel_stats
        lines.append(f"Parallel: max_conc={ps['max_concurrency']} branches={ps['parallel_tasks']} "
                     f"conflicts={ps['conflicts']} cancel={ps['cancellations']}")
    if t.graph:
        lines.append(f"Graph: valid={t.graph['valid']} order={'>'.join(t.graph['order'])}")
    if t.sub_states:
        lines.append("Sub-states: " + " ".join(f"{k}={v}" for k, v in t.sub_states.items()))
    if t.critic:
        lines.append(f"Critic: {t.critic['status']} → {t.critic.get('recommendation')} "
                     f"| failed: {t.critic.get('requirements_failed', [])[:3]}")
    for d in t.debug_log[-2:]:
        lines.append(f"Debug: {d.get('root_cause','?')[:120]}")
    if t.error:
        lines.append(f"ERROR: {t.error}")
    return "\n".join(lines)
