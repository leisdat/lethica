# core/orch_agents.py — v3.7.2 Orchestrator LLM sub-agents (split dari orchestra.py).
# Planner / Analyst / Critic / Debugger / Repair / Executor / Researcher / Builder /
# AdaptiveStrategy. Delegasi murni — tidak eksekusi sendiri. Import state dari orch_state.
import os
import re
import json
import time

from core import config, client as client_mod, tools, tags, rag, registry, soul, experience
from core import strategy as strategy_mod
from core import evolution
from core.orch_state import Task, _log, _limits


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
    # heuristik dulu: task pendek/aksi tunggal tidak perlu subtask
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
    # Panggil via facade `orchestra.*` agar monkey-patch test
    # (`orchestra._execute_serial` / `orchestra.merge_results`) terlihat.
    from core import orchestra
    if task.limits.get("max_concurrent_agents", 1) <= 1 or len(byid) <= 1:
        orchestra._execute_serial(task, byid)
    else:
        orchestra._execute_parallel(task, byid)
    orchestra.merge_results(task)
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
            for u in re.findall(r"https?://[^\s\)\]]+", sr)[:2]:
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
    from core.orch_scheduler import _unblock_ready  # v3.2: dependent BLOCKED boleh hidup lagi setelah fix
    _unblock_ready(task)
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
