# core/experience.py — v3.1 Experience-Aware Orchestration.
# Task Memory + Failure Memory + similarity/recall + quality control + metrics.
# Reuse storage v3.0: task-history.json di-upgrade in-place (key lama utuh,
# key baru nambah). TIDAK ada memory system kedua; memory bank .md (tool_memory)
# tetap terpisah utk catatan manual.
import os
import re
import json
import time
from collections import deque
from datetime import datetime, timezone

from core import config

HIST_FILE = os.path.join(config.LETHICA_DIR, "task-history.json")   # v3.0: tetap di sini
FAIL_FILE = os.path.join(config.LETHICA_DIR, "task-failures.json")  # failure memory
MAX_HIST = 300
RECENT_WINDOW = 10   # utk recent_success_rate skill/memory

_STOP = set("untuk dan atau dengan yang dari ke di pada buat bikin buatlah to the a an of for and or with that this dari".split())
_TIDAK_DIHITUNG = ("SKIP",)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _norm(text):
    """Normalisasi goal: lowercase, token alphanumeric significance-only."""
    toks = re.findall(r"[a-z0-9_]+", (text or "").lower())
    return " ".join(t for t in toks if t not in _STOP and len(t) > 1)


def _tags(text):
    toks = set(re.findall(r"[a-z0-9]{3,}", (text or "").lower()))
    return sorted(toks - _STOP)[:20]


# ── storage ──────────────────────────────────────────────────────────
def _load(path):
    if os.path.isfile(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return []
    return []


def _save(path, data):
    tmp = path + ".tmp"
    json.dump(data, open(tmp, "w", encoding="utf-8"), ensure_ascii=False)
    os.replace(tmp, path)


def all_tasks():
    return _load(HIST_FILE)


def all_failures():
    return _load(FAIL_FILE)


# ── FEATURE 1: Task Memory record (dari Task orchestra) ──────────────
def save_task_memory(task):
    """Panggil di akhir run(). Meng-upgrade entri history v3.0 (match by id)
    dengan field experience. Entri lama yang gak ketemu → append baru."""
    skills_used = list((task.skill_report or {}).get("available_skills", []))
    tools_used = sorted({a.split(":")[0] for sid, r in task.subtask_results.items()
                         for a in r.get("actions", [])})
    approach = [st.get("description", "")[:120] for st in (task.plan or {}).get("subtasks", [])]
    result = "success" if task.state == "COMPLETED" else "failure"
    rec = {
        # field lama v3.0 tetap ada (backward compat)
        "id": task.id, "task_id": task.id, "goal": task.goal[:200], "state": task.state,
        "complexity": task.complexity, "steps": task.steps,
        "tool_calls": task.tool_calls, "repairs": task.repair_count,
        "elapsed": round(task.elapsed(), 1),
        "subtasks": len((task.plan or {}).get("subtasks", [])),
        "critic_status": (task.critic or {}).get("status"),
        "error": task.error,
        # v3.1 experience fields
        "normalized_goal": _norm(task.goal),
        "tags": _tags(task.goal),
        "skills_used": skills_used, "tools_used": tools_used,
        "approach": approach,
        "subtask_ids": list(task.subtask_results.keys()),
        "result": result,
        "failures": [e for sid, r in task.subtask_results.items() for e in r.get("errors", [])][:8],
        "repairs_detail": [d for d in task.debug_log[-3:]],
        "final_solution": task.final_solution[:600] if hasattr(task, "final_solution") else
                          (task.critic or {}).get("requirements_met", [""])[0][:600] if result == "success" else "",
        "files_changed": sorted({f for sid, r in task.subtask_results.items()
                                 for f in r.get("files_changed", [])})[:20],
        "memory_hits": [h["memory_id"] for h in getattr(task, "recalled", [])],
        "memory_used_ids": list(getattr(task, "recalled_ids", [])),
        "duration_ms": int(task.elapsed() * 1000),
        "parallel_stats": getattr(task, "parallel_stats", None),
        "merged_warnings": (getattr(task, "merged", None) or {}).get("warnings", [])[:5],
        # v3.3 strategy experience (super-set; old records remain valid)
        "strategy_id": getattr(getattr(task, "strategy", None), "id", None),
        "strategy_candidates": [getattr(s, "id", s) for s in getattr(task, "strategy_candidates", [])],
        "strategy_confidence": getattr(task, "strategy_confidence", "LOW"),
        "strategy_selection": getattr(task, "strategy_selection", None),
        "strategy_switches": getattr(task, "strategy_switches", 0),
        "strategy_history": getattr(task, "strategy_history", []),
        "strategy_failure": getattr(task, "strategy_failure", None),
        "planning_metrics": getattr(task, "planning_metrics", {}),
        "skill_gaps": [g.to_dict() if hasattr(g, "to_dict") else g
                       for g in getattr(task, "skill_gaps", [])],
        "skill_evolution": getattr(task, "skill_evolution", []),
        "mem_quality": "CONFIRMED" if result == "success" else "UNVERIFIED",
        "mem_confidence": 0.7 if result == "success" else 0.2,
        "reuse_success": 0, "reuse_failure": 0,
        "created_at": _now(), "updated_at": _now(),
    }
    hist = _load(HIST_FILE)
    for i, h in enumerate(hist):
        if h.get("id") == task.id:
            hist[i] = rec
            break
    else:
        hist.append(rec)
    _save(HIST_FILE, hist[-MAX_HIST:])
    # FEATURE 3: failure memory — rekam pola gagal + fix yang terbukti
    for d in task.debug_log:
        rc, comp = d.get("root_cause", ""), d.get("component", "")
        if not rc:
            continue
        fixed = result == "success"
        fails = _load(FAIL_FILE)
        # dedupe by (root_cause[:80]) — update streak kalau sama
        for fm in fails:
            if fm["root_cause"][:80] == rc[:80]:
                fm["count"] = fm.get("count", 1) + 1
                fm["updated_at"] = _now()
                fm["success_after_fix"] = fixed
                fm["fix"] = d.get("fix_steps", fm.get("fix", ""))
                break
        else:
            fails.append({"id": f"f{int(time.time())}-{len(fails)}",
                          "failure_type": _classify_failure(rc, task.error or ""),
                          "context": (task.goal[:120]),
                          "root_cause": rc[:400],
                          "component": comp[:80],
                          "fix": d.get("fix_steps", [])[:6],
                          "success_after_fix": fixed,
                          "count": 1, "created_at": _now(), "updated_at": _now()})
        _save(FAIL_FILE, fails[-200:])
    return rec


def _classify_failure(rc, err):
    s = (rc + " " + (err or "")).lower()
    for pat, name in [(r"timeout|waktu", "timeout"), (r"path|direktori|fold", "path_error"),
                      (r"quota|429|budget", "quota"), (r"parse|json", "parse_error"),
                      (r"model|provider|unauthor|401|402", "model_unavailable"),
                      (r"sandbox|permission|danger", "safety_block"),
                      (r"dependensi|dependency|block", "dependency_fail"),
                      (r"bukti|evidence|tanpa tool|klaim", "evidence_gap")]:
        if re.search(pat, s):
            return name
    return "unknown"


# ── FEATURE 2: similarity / recall ───────────────────────────────────
def _jaccard(a, b):
    A, B = set(a.split()), set(b.split())
    return len(A & B) / len(A | B) if A and B else 0.0


def recall(goal, top_k=3, min_sim=0.25):
    """Cari task memory yang relevan. Bukti, bukan kebenaran: similarity murni
    leksikal + bonus tag; entri STALE/lama tetap boleh muncul (dengan flag)."""
    q = _norm(goal)
    out = []
    for h in all_tasks():
        sim = _jaccard(q, h.get("normalized_goal") or _norm(h.get("goal", "")))
        # bonus: tag overlap (lebih kuat dari kata umum)
        tq = set(_tags(goal)) & set(h.get("tags", []))
        if tq:
            sim = min(1.0, sim + 0.1 * len(tq))
        if sim >= min_sim:
            out.append({
                "memory_id": h.get("id"), "similarity": round(sim, 2),
                "relevance": "high" if sim >= 0.55 else "medium",
                "goal": h.get("goal", "")[:100], "result": h.get("result", "?"),
                "approach": h.get("approach", [])[:5],
                "strategy_id": h.get("strategy_id"),
                "strategy_confidence": h.get("strategy_confidence", "LOW"),
                "skills_used": h.get("skills_used", [])[:5],
                "mem_confidence": h.get("mem_confidence", 0.5),
                "mem_quality": h.get("mem_quality", "UNVERIFIED"),
                "final_solution": h.get("final_solution", "")[:200],
                "age_days": round((time.time() - _ts(h.get("created_at"))) / 86400, 1),
            })
    out.sort(key=lambda x: (-x["similarity"], -x["mem_confidence"]))
    return {"similar_tasks": out[:top_k]}


def recall_failures(goal, top_k=3):
    """Failure memory relevan — dipakai Planner DAN Debugger."""
    q = set(_tags(goal))
    out = []
    for f in all_failures():
        sc = len(q & set(_tags(f["context"]))) + (2 if f.get("success_after_fix") else 0)
        if q and sc:
            out.append((sc, f))
    out.sort(key=lambda x: -x[0])
    return [f for _, f in out[:top_k]]


def _ts(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").timestamp()
    except Exception:
        return 0.0


# ── FEATURE 11: memory quality control ───────────────────────────────
# UNVERIFIED → CONFIRMED (critic pass, sukses) → REUSABLE (reuse sukses ≥2)
# → STALE (umur >60hr tanpa reuse atau reuse gagal berulang)
def requality():
    """Dipanggil periodic (mis. tiap start Lethica): update mem_quality +
    confidence dari bukti historis. Tidak menghapus apa pun."""
    hist = _load(HIST_FILE)
    changed = 0
    for h in hist:
        age = (time.time() - _ts(h.get("created_at"))) / 86400
        conf = h.get("mem_confidence", 0.5)
        rs, rf = h.get("reuse_success", 0), h.get("reuse_failure", 0)
        if rs >= 2 and h.get("result") == "success":
            q = "REUSABLE"; conf = min(1.0, conf + 0.1)
        elif rf >= 2:
            q = "UNVERIFIED"; conf = max(0.1, conf - 0.2)
        elif h.get("result") == "success":
            q = "CONFIRMED"
        else:
            q = "UNVERIFIED"
        if age > 60 and q != "REUSABLE":
            q = "STALE"
        if q != h.get("mem_quality") or conf != h.get("mem_confidence"):
            h["mem_quality"], h["mem_confidence"] = q, round(conf, 2)
            h["updated_at"] = _now()
            changed += 1
    if changed:
        _save(HIST_FILE, hist)
    return changed


# ── FEATURE 12: feedback loop ────────────────────────────────────────
def feedback(task_id, outcome, memory_ids=None, failure_reason=""):
    """Sinyal setelah memakai memory: task yang recall-memakai memory X sukses/gagal →
    update confidence memory X. Ini yang mencegah Lethica percaya buta memori lama."""
    hist = _load(HIST_FILE)
    touched = []
    by = {h.get("id"): h for h in hist}
    cur = by.get(task_id, {})
    for mid in (memory_ids or cur.get("memory_used_ids", [])):
        h = by.get(mid)
        if not h:
            continue
        if outcome == "success":
            h["reuse_success"] = h.get("reuse_success", 0) + 1
            h["mem_confidence"] = round(min(1.0, h.get("mem_confidence", 0.5) + 0.1), 2)
            if h.get("mem_quality") == "CONFIRMED" and h.get("reuse_success", 0) >= 2:
                h["mem_quality"] = "REUSABLE"
        else:
            h["reuse_failure"] = h.get("reuse_failure", 0) + 1
            h["mem_confidence"] = round(max(0.1, h.get("mem_confidence", 0.5) - 0.2), 2)
            if failure_reason:
                h.setdefault("misleading_reasons", []).append(failure_reason[:120])
            if h["reuse_failure"] >= 2:
                h["mem_quality"] = "UNVERIFIED"
        h["updated_at"] = _now()
        touched.append(mid)
    if touched:
        _save(HIST_FILE, hist)
    return touched


# ── FEATURE 10: metrics ──────────────────────────────────────────────
def metrics():
    hist = _load(HIST_FILE)
    if not hist:
        return {"tasks": 0}
    # v3.1: entri pra-v3.1 tanpa field `result` TIDAK dihitung di rate
    # (dulu: hasilkan 0.0 palsu karena entri lama counted sbg bukan-success)
    rated = [h for h in hist if h.get("result")]
    n = max(1, len(rated))
    succ = [h for h in rated if h.get("result") == "success"]
    with_mem = [h for h in rated if h.get("memory_used_ids")]
    with_mem_succ = [h for h in with_mem if h.get("result") == "success"]
    from collections import Counter
    ftypes = Counter(_classify_failure(f.get("root_cause", ""), f.get("component", ""))
                     for f in all_failures())
    rec_fail = [f for f in all_failures() if f.get("count", 1) >= 2]
    durs = [h.get("duration_ms", 0) for h in rated if h.get("duration_ms")]
    return {
        "tasks": len(rated),
        "success_rate": round(len(succ) / n, 3),
        "failed": len(rated) - len(succ),
        "avg_retries": round(sum(h.get("repairs", 0) for h in rated) / n, 2),
        "repair_rate": round(sum(1 for h in rated if h.get("repairs", 0) > 0) / n, 3),
        "avg_duration_ms": int(sum(durs) / len(durs)) if durs else 0,
        "memory_hit_rate": round(len(with_mem) / n, 3),
        "memory_success_rate": round(len(with_mem_succ) / len(with_mem), 3) if with_mem else None,
        # NOTE (anti-klaim palsu): memory_success_rate BUKAN klaim kegunaan —
        # baru berarti setelah n cukup (lihat with_mem < 10 → low_sample).
        "memory_sample_warning": (len(with_mem) < 10),
        "failure_patterns": dict(ftypes.most_common(5)),
        "recurring_failures": [{"type": f["failure_type"], "count": f["count"]} for f in rec_fail][:5],
    }


def summary():
    m = metrics()
    lines = [f"Task memory: {m.get('tasks', 0)} task | success_rate={m.get('success_rate')} "
             f"| memory_hit_rate={m.get('memory_hit_rate')}"]
    if m.get("memory_success_rate") is not None:
        tag = " (SAMPLE KECIL — jangan percaya)" if m.get("memory_sample_warning") else ""
        lines.append(f"memory utk task dengan recall: sukses {m['memory_success_rate']}{tag}")
    if m.get("failure_patterns"):
        lines.append("pola failure: " + " · ".join(f"{k}×{v}" for k, v in m["failure_patterns"].items()))
    return "\n".join(lines)
