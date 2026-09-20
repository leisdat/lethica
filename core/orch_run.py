# core/orch_run.py — v3.7.2 Orchestrator top-level run loop + reporting (split dari orchestra.py).
# Mengikat seluruh sub-modul: agents + scheduler + state. Tidak ada logika baru.
import os
import re
import time

from core import config, experience, registry, learning, strategy as strategy_mod
from core.orch_state import Task, _log
from core.orch_agents import (
    planner, skill_analyst, adaptive_strategy, _switch_strategy, researcher,
    build_missing_skills, critic, debugger, repair,
)
from core.orch_scheduler import (
    graph_validate, classify_subtask, match_capability, merge_results,
    _execute_serial, _execute_parallel, _retry_failed, redecompose_independent,
    _deps,
)


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
