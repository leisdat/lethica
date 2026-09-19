# core/registry.py — v3.0 Skill Registry persisten + builder + evaluator.
# Sumber kebenaran: ~/lethica/skill-registry.json (BUKAN prompt LLM).
# Status lama tetap kompatibel; v3.4 menambah immutable version lineage.
import os
import re
import json
import time
import shutil
from datetime import datetime, timezone

from core import config, tools

REG_FILE = os.path.join(config.LETHICA_DIR, "skill-registry.json")
STATUSES = ("unverified", "verified", "degraded", "broken", "deprecated")

# ambang status (dipakai record_use & evaluate)
_VERIFY_MIN_USAGE = 3     # sukses beruntun min. sebelum jadi 'verified'
_VERIFY_MIN_RATE = 0.8
_DEGRADED_RATE = 0.5


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ── store ───────────────────────────────────────────────────────────
def _load_raw():
    if os.path.isfile(REG_FILE):
        try:
            with open(REG_FILE, encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("skills"), dict):
                return d
        except Exception:
            pass
    return {"version": 1, "updated": None, "skills": {}}


def _save_raw(d):
    d["updated"] = _now()
    tmp = REG_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=0)
    os.replace(tmp, REG_FILE)


def entries():
    """Semua entri registry: {relkey: meta}."""
    return _load_raw()["skills"]


def get(name):
    d = _load_raw()["skills"]
    if name in d:
        return d[name]
    # fallback basename (sama seperti alias skill loader)
    hits = [k for k in d if k.split("/")[-1] == name]
    if len(hits) == 1:
        return d[hits[0]]
    return None


def _new_meta(name, description="", capabilities=None):
    return {
        "name": name, "version": 1, "description": description[:200],
        "capabilities": capabilities or [], "dependencies": [], "tools": [],
        "examples": [], "tests": [], "confidence": 0.0, "success_rate": 0.0,
        "usage_count": 0, "failure_count": 0, "last_used": None,
        "last_verified": None, "status": "unverified",
        # v3.1 bukti lebih kaya (kompatibel: field lama utuh)
        "success_count": 0, "recent": [], "failure_streak": 0,
        "test_pass_rate": 0.0,
        # v3.4: version records are append-only; old fields remain canonical
        "versions": [], "active_version": None, "lineage": [],
        "evolution_status": "UNVERIFIED", "evolution_evidence": [],
    }


RECENT_WINDOW = 10
STALE_DAYS = 60


def _recent_rate(m):
    """Success rate window N terakhir — terpisah dari lifetime."""
    rec = m.get("recent") or []
    return round(sum(1 for x in rec if x) / len(rec), 3) if rec else 0.0


def _age_days(iso):
    if not iso:
        return None
    try:
        from datetime import datetime, timezone
        t = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        import time as _t
        return (_t.time() - t.timestamp()) / 86400
    except Exception:
        return None


def health(name):
    """FEATURE 7 — derived health (TIDAK menyimpan, TIDAK menghapus skill):
    HEALTHY   confidence tinggi + recent sukses + fresh
    DEGRADED  gagal baru2 ini / rate turun
    BROKEN    gagal berulang
    STALE     lama tak terverifikasi (>= STALE_DAYS)
    UNVERIFIED bukti kurang"""
    m = get(name)
    if not m:
        return None
    age = _age_days(m.get("last_verified"))
    if age is not None and age > STALE_DAYS and m.get("status") != "broken":
        return "STALE"
    st = m.get("status")
    if st == "broken" or (m.get("usage_count", 0) >= 3 and m.get("success_rate", 1) < _DEGRADED_RATE):
        return "BROKEN"
    if st == "degraded" or (m.get("usage_count", 0) >= 3 and m.get("success_rate", 1) < _VERIFY_MIN_RATE):
        return "DEGRADED"
    if st == "verified" and (m.get("confidence") or 0) >= 0.5:
        return "HEALTHY"
    return "UNVERIFIED"


def rank(req, candidates):
    """FEATURE 8 — ranking kandidat skill berbasis BUKTI (bukan arbitrary):
    capability-match, confidence, recent_success, test_pass, deps-availability,
    failure-history, freshness. Return terurut + bukti per kandidat."""
    import time as _t
    out = []
    for k in candidates:
        m = get(k)
        if not m:
            continue
        ev = []
        cap = 1.0 if (req and req.lower().replace(" ", "_") in (m["name"] + " " + " ".join(m["capabilities"]) + " " + m["description"]).lower().replace(" ", "_")) else 0.3
        if cap == 1.0:
            ev.append("matched capability")
        rr = _recent_rate(m)
        if rr >= 0.8 and m.get("recent"):
            ev.append("recent successful executions")
        if m.get("last_verified") and (_age_days(m.get("last_verified")) or 999) <= 30:
            ev.append("verified recently")
        deps_ok = 1.0 if not m.get("dependencies") else 0.5
        fresh = max(0.0, 1.0 - (_age_days(m.get("last_used")) or 365) / 180.0)
        fail_pen = min(0.4, m.get("failure_streak", 0) * 0.15)
        score = round(0.25 * cap + 0.20 * (m.get("confidence") or 0) + 0.20 * rr
                      + 0.15 * m.get("test_pass_rate", 0.0) + 0.10 * deps_ok
                      + 0.10 * fresh - fail_pen, 3)
        ev.append(f"lifetime={m.get('success_rate', 0)} recent={rr} streak_gagal={m.get('failure_streak', 0)}")
        out.append({"skill": m["name"], "score": score, "evidence": ev,
                    "health": health(m["name"])})
    out.sort(key=lambda x: -x["score"])
    return out


# ── seed dari skill index yang ADA (v2.9.7) ─────────────────────────
def _purpose_desc(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            head = f.read(900)
    except Exception:
        return ""
    m = re.search(r"##\s*Purpose\s*\n+(.+)", head)
    if m:
        return m.group(1).strip()[:200]
    for ln in head.splitlines():
        ln = ln.strip()
        if ln and not ln.startswith(("#", "---", "name:", "description:")):
            return ln[:200]
    return ""


def ensure_seeded():
    """Sinkronkan registry dengan tools._SKILL_INDEX. Entri lama dipertahankan
    (idempoten) — ini yang bikin registry bisa di-trust sebagai sumber metrik."""
    tools._build_skill_index()
    d = _load_raw()
    added = 0
    migrated = False
    for relkey, path in tools._SKILL_INDEX.items():
        if relkey in d["skills"]:
            m = d["skills"][relkey]
            defaults = {"versions": [], "active_version": None, "lineage": [],
                        "evolution_status": "UNVERIFIED", "evolution_evidence": []}
            for key, value in defaults.items():
                if key not in m:
                    m[key] = value
                    migrated = True
            continue
        top = relkey.split("/")[0]
        meta = _new_meta(relkey, _purpose_desc(path), capabilities=[top])
        d["skills"][relkey] = meta
        added += 1
    # skill yang hilang dari disk → deprecated (jangan hapus: historinya dipakai)
    for k in list(d["skills"]):
        m = d["skills"][k]
        defaults = {"versions": [], "active_version": None, "lineage": [],
                    "evolution_status": "UNVERIFIED", "evolution_evidence": []}
        for key, value in defaults.items():
            if key not in m:
                m[key] = value
                migrated = True
        if k not in tools._SKILL_INDEX and d["skills"][k]["status"] != "deprecated":
            if not os.path.isfile(tools._SKILL_INDEX.get(k, os.path.join(tools.SKILL_DIR, k, "SKILL.md"))):
                d["skills"][k]["status"] = "deprecated"
    if added or migrated:
        _save_raw(d)
    return {"total": len(d["skills"]), "added": added}


# ── metrik / status ─────────────────────────────────────────────────
def _recompute_status(m):
    u, f = m["usage_count"], m["failure_count"]
    m["success_rate"] = round((u - f) / u, 3) if u else 0.0
    old = m["status"]
    if old == "deprecated":
        return
    if u >= _VERIFY_MIN_USAGE and m["success_rate"] >= _VERIFY_MIN_RATE:
        m["status"] = "verified"
        m["confidence"] = max(m["confidence"], round(m["success_rate"], 2))
    elif u >= _VERIFY_MIN_USAGE and m["success_rate"] >= _DEGRADED_RATE:
        m["status"] = "degraded"
    elif u >= _VERIFY_MIN_USAGE:
        m["status"] = "broken"
    else:
        m["status"] = old if old in ("verified", "degraded", "broken") else "unverified"


def record_use(names, success=True):
    """Learning signal: skill dipakai (sukses/gagal). Dipanggil orchestrator
    & bisa dipakai manual. Return daftar skill yang di-update."""
    d = _load_raw()
    touched = []
    for n in names or []:
        m = d["skills"].get(n)
        if m is None:
            hits = [k for k in d["skills"] if k.split("/")[-1] == n]
            m = d["skills"][hits[0]] if len(hits) == 1 else None
        if m is None:
            continue
        m["usage_count"] += 1
        m["last_used"] = _now()
        # v3.1: window recent + success_count + streak (kompat: delta confidence lama utuh)
        m["recent"] = (m.get("recent") or [])[-(RECENT_WINDOW - 1):] + [1 if success else 0]
        if success:
            m["last_verified"] = _now()
            m["success_count"] = m.get("success_count", 0) + 1
            m["failure_streak"] = 0
            m["confidence"] = round(min(1.0, m["confidence"] + 0.1), 2)
        else:
            m["failure_count"] += 1
            m["failure_streak"] = m.get("failure_streak", 0) + 1
            m["confidence"] = round(max(0.0, m["confidence"] - 0.2), 2)
        _recompute_status(m)
        touched.append(f"{m['name']}:{m['status']}")
    if touched:
        _save_raw(d)
    return touched


def update(name, **fields):
    d = _load_raw()
    m = d["skills"].get(name)
    if not m:
        return False
    for k, v in fields.items():
        if k in m and k != "name":
            m[k] = v
    _recompute_status(m)
    _save_raw(d)
    return True


# ── analisis kebutuhan skill (Skill Analyst tanpa halusinasi) ────────
def analyze(requirements):
    """Cocokkan daftar kemampuan yang dibutuhkan vs registry. Semua keputusan
    berbasis data nyata registry — BUKAN tebakan LLM."""
    reg = entries()
    available, outdated, low_conf, missing = [], [], [], []
    for req in requirements or []:
        rq = req.strip().lower().replace(" ", "_")
        best = None
        for k, m in reg.items():
            hay = (k + " " + m["name"].split("/")[-1] + " " + m["description"] + " "
                   + " ".join(m["capabilities"])).lower().replace(" ", "_")
            if rq and (rq in hay or hay.split("/")[-1].replace("_", " ") in req.lower()):
                if best is None or m["success_rate"] > reg[best]["success_rate"]:
                    best = k
        if best is None:
            missing.append(req)
            continue
        # v3.1: ranked evidence-based, bukan sekadar sukses-rate tertinggi
        ranked = rank(req, [k for k, v in reg.items()
                            if req.lower().replace(" ", "_") in
                            (k + " " + v["description"] + " " + " ".join(v["capabilities"])).lower().replace(" ", "_")])
        best = ranked[0]["skill"] if ranked else best
        m = reg[best]
        if m["status"] in ("degraded", "broken", "deprecated"):
            outdated.append({"skill": best, "status": m["status"],
                             "success_rate": m["success_rate"]})
        elif m["confidence"] < 0.3:
            low_conf.append({"skill": best, "confidence": m["confidence"]})
        else:
            available.append(best)
    action = "EXECUTE"
    if missing:
        action = "RESEARCH_AND_BUILD_SKILLS"
    elif outdated:
        action = "UPDATE_SKILLS"
    elif low_conf:
        action = "EXECUTE_WITH_CAUTION"
    return {"required_skills": list(requirements or []),
            "available_skills": available, "missing_skills": missing,
            "outdated_skills": outdated, "low_confidence": low_conf,
            "action": action}


# ── Skill Builder + Evaluator ───────────────────────────────────────
def build_skill(name, layer, content, description="", capabilities=None,
                overwrite=False):
    """Buat skill baru dari hasil riset → SKILL.md + entri 'unverified'.
    Skill BARU TIDAK otomatis dipercaya: status awal unverified, confidence 0."""
    name = re.sub(r"[^a-zA-Z0-9_\-]", "_", (name or "").strip())[:60]
    layer = re.sub(r"[^a-zA-Z0-9_\-]", "_", (layer or "generated").strip())[:60]
    if not name:
        return {"ok": False, "error": "nama skill kosong"}
    d = os.path.join(tools.SKILL_DIR, layer, name)
    if os.path.isfile(os.path.join(d, "SKILL.md")) and not overwrite:
        return {"ok": False, "error": f"skill {layer}/{name} sudah ada (overwrite=True untuk timpa)"}
    os.makedirs(d, exist_ok=True)
    body = content if content.lstrip().startswith("#") else f"# {name}\n\n## Purpose\n{description or name}\n\n{content}"
    with open(os.path.join(d, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(body)
    ensure_seeded()
    reg = _load_raw()
    key = f"{layer}/{name}"
    meta = reg["skills"].get(key) or _new_meta(key, description or _purpose_desc(os.path.join(d, "SKILL.md")),
                                                capabilities=capabilities or [layer])
    meta["status"] = "unverified"
    meta["confidence"] = 0.0
    reg["skills"][key] = meta
    _save_raw(reg)
    return {"ok": True, "skill": key, "path": os.path.join(d, "SKILL.md")}


def evaluate_skill(name, tests):
    """Evaluator: jalankan daftar test command (shell) utk sebuah skill.
    tests = ['python3 x/test.py', ...]. Update success_rate + status dari
    hasil EKSEKUSI NYATA. Return report."""
    if isinstance(tests, str):
        tests = [t for t in re.split(r"[\n;]+", tests) if t.strip()]
    m = get(name)
    if not m:
        return {"ok": False, "error": f"skill '{name}' tidak ada di registry"}
    passed, failed, logs = 0, 0, []
    for t in tests:
        r = tools.tool_run_command(t, timeout=120)
        ok = "[exit=0]" in r
        passed += 1 if ok else 0
        failed += 0 if ok else 1
        logs.append(("PASS " if ok else "FAIL ") + t[:80])
    total = passed + failed
    rate = round(passed / total, 3) if total else 0.0
    status = ("verified" if rate >= _VERIFY_MIN_RATE and total >= _VERIFY_MIN_USAGE
              else "degraded" if rate >= _DEGRADED_RATE and total else "unverified")
    update(name, tests=[{"cmd": t} for t in tests],
           **{"status": status, "confidence": rate, "test_pass_rate": rate})
    # seed usage khusus evaluation: pakai jalur update manual biar tidak
    # mengacaukan usage_count nyata dari eksekusi task
    return {"ok": True, "skill": m["name"], "tests": total, "passed": passed,
            "failed": failed, "success_rate": rate, "status": status, "log": logs}


# ── ringkasan untuk prompt / slash ──────────────────────────────────
def summary():
    reg = entries()
    by = {s: 0 for s in STATUSES}
    for m in reg.values():
        by[m["status"]] = by.get(m["status"], 0) + 1
    lines = [f"Skill registry: {len(reg)} skill @ {REG_FILE}",
             "Status: " + " · ".join(f"{k}={v}" for k, v in by.items() if v)]
    worst = sorted((m for m in reg.values() if m["usage_count"] >= 2),
                   key=lambda m: (m["success_rate"], -m["failure_count"]))[:5]
    hh = {}
    for m in reg.values():
        h = health(m["name"])
        hh[h] = hh.get(h, 0) + 1
    lines.insert(1, "Health: " + " · ".join(f"{k}={v}" for k, v in sorted(hh.items())))
    if worst:
        lines.append("Paling bermasalah:")
        lines += [f"  {m['name']} [{m['status']}] rate={m['success_rate']} "
                  f"fail={m['failure_count']} u={m['usage_count']}" for m in worst]
    return "\n".join(lines)
