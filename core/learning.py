# core/learning.py - PEMBELAJARAN OTOMATIS (v2.9)
# Refleksi diri per operasi, simpan pelajaran, perbarui strategi,
# identifikasi pola, sarikan templat. Trend tiap N operasi.
# Skor Siluman 0-100%: <CORRECT koreksi, <ABORT pembatalan.
import os
import json
import time

from core import config

LESSONS_DIR = os.path.join(config.LETHICA_DIR, "lessons")
os.makedirs(LESSONS_DIR, exist_ok=True)
LESSONS_FILE = os.path.join(LESSONS_DIR, "lessons.jsonl")
STATE_FILE = os.path.join(LESSONS_DIR, "state.json")

def _cfg(key, dflt):
    try:
        return config.CFG.get("learning", {}).get(key, dflt)
    except Exception:
        return dflt

CORRECT_THRESHOLD = _cfg("correct_threshold", 80)
ABORT_THRESHOLD   = _cfg("abort_threshold", 60)
TREND_INTERVAL    = _cfg("trend_interval", 10)
ENABLED           = _cfg("enabled", True)

class _Turn:
    __slots__ = ("snap", "verdict", "truncated")
    def __init__(self):
        self.snap = {}
        self.verdict = None
        self.truncated = False

_CURRENT = _Turn()

def begin_turn():
    if not ENABLED:
        return
    from core import stats
    snap = {}
    for name, s in stats.TOOL_STATS.items():
        snap[name] = (s.get("calls", 0), s.get("errors", 0))
    _CURRENT.snap = snap
    _CURRENT.verdict = None
    _CURRENT.truncated = False

def record_verdict(v):
    if ENABLED and v:
        _CURRENT.verdict = v

def record_truncation():
    if ENABLED:
        _CURRENT.truncated = True

def _diff_stats():
    from core import stats
    calls = errors = 0
    tb = {}
    for name, s in stats.TOOL_STATS.items():
        pc, pe = _CURRENT.snap.get(name, (0, 0))
        dc = s.get("calls", 0) - pc
        de = s.get("errors", 0) - pe
        if dc > 0 or de > 0:
            tb[name] = {"calls": dc, "errors": de}
            calls += dc
            errors += de
    return calls, errors, tb

def _silent_score(calls, errors):
    s = 100.0
    if calls:
        s -= (errors / calls) * 60.0
    if _CURRENT.verdict == "REVISE":
        s -= 25.0
    if _CURRENT.truncated:
        s -= 15.0
    return max(0.0, min(100.0, s))

def _load_state():
    try:
        if os.path.isfile(STATE_FILE):
            with open(STATE_FILE, encoding="utf-8") as f:
                st = json.load(f)
        else:
            st = {}
    except Exception:
        st = {}
    st.setdefault("ops", [])
    st.setdefault("lessons", [])
    st.setdefault("templates", [])
    st.setdefault("op_counter", 0)
    st.setdefault("last_bucket", 0)
    st.setdefault("strategy", "")
    st.setdefault("failure_points", [])
    st.setdefault("avg_score", 100.0)
    st.setdefault("turns", 0)
    return st

def _save_state(st):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=1)
    except Exception:
        pass

def _append_lesson(op, lesson):
    try:
        with open(LESSONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": op["ts"], "score": op["score"],
                                "goal": op["goal"], "lesson": lesson}) + "\n")
    except Exception:
        pass

def _extract_lesson(op):
    bits = []
    if op["errors"]:
        worst = sorted(op["tools"].items(), key=lambda x: -x[1]["errors"])[:3]
        detail = ", ".join(f"{n}({v['errors']}/{v['calls']})" for n, v in worst if v["errors"])
        bits.append(f"error tool: {detail or str(op['errors'])+'x'} - verifikasi path/target & izin sebelum eksekusi")
    if op["verdict"] == "REVISE":
        bits.append("reflection REVISE - jangan klaim tanpa bukti tool; jalankan dulu baru simpulkan")
    if op["truncated"]:
        bits.append("output kepotong - pecah tugas, kurangi verbose, pipe output panjang ke file")
    if not bits:
        return None
    return " || ".join(bits)

def _extract_template(op):
    if op["score"] >= 95 and op["calls"] >= 2 and not op["errors"]:
        seq = " -> ".join(sorted(op["tools"].keys()))
        return f"templat sukses [{seq}] skor {op['score']}%: pola tool ini terbukti bersih, reusable"
    return None

def _analyze_trends(ops):
    last = ops[-TREND_INTERVAL:]
    if not last:
        return {"avg": 100.0, "err_rate": 0.0, "revise": 0, "trunc": 0,
                "strategy": "stabil", "failure_points": []}
    avg = sum(o["score"] for o in last) / len(last)
    calls = sum(o["calls"] for o in last)
    errors = sum(o["errors"] for o in last)
    err_rate = (errors / calls) if calls else 0.0
    revise = sum(1 for o in last if o.get("verdict") == "REVISE")
    trunc = sum(1 for o in last if o.get("truncated"))
    agg = {}
    for o in last:
        for n, v in o.get("tools", {}).items():
            a = agg.setdefault(n, [0, 0])
            a[0] += v["calls"]; a[1] += v["errors"]
    fps = []
    for n, (c, e) in sorted(agg.items(), key=lambda x: -(x[1][1] / max(1, x[1][0]))):
        if e:
            fps.append({"tool": n, "calls": c, "errors": e, "rate": round(e / c, 2)})
    fps = fps[:5]
    strat = []
    if err_rate > 0.2:
        strat.append(f"tingkat error tool {err_rate:.0%} - cek asumsi/path/izin SEBELUM eksekusi")
    if fps:
        strat.append("hindari pola gagal di: " + ", ".join(f["tool"] for f in fps))
    if revise > len(last) * 0.3:
        strat.append("reflection sering REVISE - sertakan bukti tool sebelum klaim final")
    if trunc > len(last) * 0.3:
        strat.append("output sering kepotong - pecah tugas / terse mode")
    if avg < CORRECT_THRESHOLD:
        strat.append(f"skor rata {avg:.0f}% < {CORRECT_THRESHOLD}% - perlambat, validasi tiap langkah")
    return {"avg": round(avg, 1), "err_rate": round(err_rate, 2),
            "revise": revise, "trunc": trunc,
            "strategy": " | ".join(strat) if strat else "stabil",
            "failure_points": fps}

def end_turn(goal="", reply=""):
    if not ENABLED:
        return 100.0, "ok", {}
    calls, errors, tb = _diff_stats()
    score = _silent_score(calls, errors)
    st = _load_state()
    op = {
        "ts": time.time(),
        "goal": (goal or "")[:160],
        "score": round(score, 1),
        "calls": calls,
        "errors": errors,
        "verdict": _CURRENT.verdict,
        "truncated": _CURRENT.truncated,
        "tools": tb,
    }
    st["ops"].append(op)
    st["ops"] = st["ops"][-200:]
    st["turns"] = st.get("turns", 0) + 1
    st["op_counter"] = st.get("op_counter", 0) + max(1, calls)
    lesson = _extract_lesson(op)
    if lesson:
        st["lessons"].append({"ts": op["ts"], "score": op["score"], "text": lesson})
        st["lessons"] = st["lessons"][-60:]
        _append_lesson(op, lesson)
    tmpl = _extract_template(op)
    if tmpl:
        st["templates"].append({"ts": op["ts"], "text": tmpl})
        st["templates"] = st["templates"][-30:]
    bucket = st["op_counter"] // TREND_INTERVAL
    if bucket > st.get("last_bucket", 0):
        st["last_bucket"] = bucket
        tr = _analyze_trends(st["ops"])
        st["strategy"] = tr["strategy"]
        st["failure_points"] = tr["failure_points"]
        st["avg_score"] = tr["avg"]
        st["trend_at"] = st["op_counter"]
    st["last_score"] = op["score"]
    _save_state(st)
    action = "ok"
    if score < ABORT_THRESHOLD:
        action = "abort"
    elif score < CORRECT_THRESHOLD:
        action = "correct"
    return score, action, st

def inject_strategy(messages):
    if not ENABLED:
        return
    try:
        st = _load_state()
        note = []
        if st.get("strategy") and st["strategy"] != "stabil":
            note.append("STRATEGI AKTIF: " + st["strategy"])
        if st.get("last_score", 100) < CORRECT_THRESHOLD:
            note.append(f"skor turn lalu {st['last_score']}% < {CORRECT_THRESHOLD}% - koreksi diri, validasi bukti")
        if note:
            messages[-1]["content"] += "\n\n## LEARNING FEEDBACK\n" + "\n".join(note)
    except Exception:
        pass

def summary_text():
    st = _load_state()
    ops = st.get("ops", [])
    if not ops:
        return ("Pembelajaran otomatis: belum ada operasi tercatat.\n"
                f"threshold koreksi <{CORRECT_THRESHOLD}% | batal <{ABORT_THRESHOLD}% | tren tiap {TREND_INTERVAL} op")
    last = ops[-1]
    lines = [
        f"Skor Siluman turn terakhir : {last['score']}%",
        f"Rata-rata (window {TREND_INTERVAL})   : {st.get('avg_score', last['score'])}%",
        f"Total operasi tercatat     : {st.get('op_counter', 0)}",
        f"Turn diproses              : {st.get('turns', 0)}",
        f"Pelajaran tersimpan        : {len(st.get('lessons', []))}",
        f"Templat tersarikan         : {len(st.get('templates', []))}",
        f"Strategi aktif             : {st.get('strategy') or '(stabil)'}",
    ]
    fps = st.get("failure_points", [])
    if fps:
        lines.append("Titik kegagalan:")
        for f in fps:
            lines.append(f"  - {f['tool']}: {f['errors']}/{f['calls']} error ({int(f['rate']*100)}%)")
    recent = st.get("lessons", [])[-3:]
    if recent:
        lines.append("Pelajaran terbaru:")
        for l in recent:
            lines.append(f"  - [{l['score']}%] {l['text'][:140]}")
    return "\n".join(lines)
