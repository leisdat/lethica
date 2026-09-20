# core/orch_scheduler.py — v3.7.2 Orchestrator scheduler/DAG/parallel (split dari orchestra.py).
# Dependency-aware, bounded, conflict-safe. State paralel di-guard task.lock.
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from core import config, client as client_mod, experience, registry, soul, tools, tags
from core.orch_state import Task, _log
from core import orch_agents
from core.orch_agents import run_subtask, _run_tools_in  # noqa: E402

# Referensi module (bukan binding statis) agar override test
# `orch_agents.executor = fn` terlihat oleh scheduler.
_executor_orig = orch_agents.executor


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
    future = None  # type: ignore[assignment]
    def __init__(self, sid, st, client):
        self.sid, self.st, self.client = sid, st, client
        self.request_cancel = False
        self.running_writer = st["type"] in ("WRITE", "DESTRUCTIVE", "MIXED")
        self.writes = predict_writes(st)


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
            res = orch_agents.executor(task, st)
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
    if orch_agents.executor is not _executor_orig:      # di-monkeypatched (deterministic test)
        res = orch_agents.executor(task, w.st)
    else:
        res = run_subtask(task, w.st, w.client, counter)
    with task.lock:
        task.tool_calls += counter["n"]
        task.agent_calls = getattr(task, "agent_calls", 0) + 1
    return res


def _run_serial_one(task, st):
    counter = {"n": 0}
    try:
        res = orch_agents.executor(task, st) if orch_agents.executor is not _executor_orig \
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
            res = orch_agents.executor(task, st)
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
                task.subtask_results[sid] = orch_agents.executor(task, wave[sid])
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
