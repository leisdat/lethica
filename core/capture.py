# core/capture.py — v3.6.0 Entity Extraction + Normalization + Resolution
#
# Menjembatani task/evidence nyata → Knowledge Graph (core/graph.py).
# Tidak menyentuh storage graph langsung: SEMUA lewat graph.* API.
#
# Prinsip anti-fabrikasi:
#   - Deterministik dulu (regex/lexicon). LLM opsional, DAN setiap relasi LLM
#     WAJIB menyertakan kutipan bukti yang benar-benar ada di teks sumber;
#     kalau kutipan tidak ditemukan → relasi DIBUANG.
#   - Entity ambigu TIDAK digabung otomatis (POSSIBLE_MATCH disimpan, bukan di-merge).
#   - Korelasi bukan kausalitas: hanya relasi yang eksplisit dalam bukti.
import os
import re

from core import graph as G

# ── lexicon deterministik (tech yang realistis di lingkungan operator) ──
PACKAGE_LEX = {
    "next.js": "PACKAGE", "nextjs": "PACKAGE", "next": "PACKAGE", "react": "PACKAGE",
    "node": "PACKAGE", "nodejs": "PACKAGE", "npm": "TOOL", "pip": "TOOL",
    "python": "PACKAGE", "python3": "PACKAGE", "postgres": "SERVICE",
    "postgresql": "SERVICE", "sqlite": "SERVICE", "redis": "SERVICE", "nginx": "SERVICE",
    "sshd": "SERVICE", "ssh": "TOOL", "termux": "ENVIRONMENT", "android": "ENVIRONMENT",
    "linux": "ENVIRONMENT", "ubuntu": "ENVIRONMENT", "proot": "TOOL",
    "playwright": "PACKAGE", "selenium": "PACKAGE", "puppeteer": "PACKAGE",
    "chromium": "PACKAGE", "chrome": "PACKAGE", "frida": "TOOL", "nmap": "TOOL",
    "wireshark": "TOOL", "ghidra": "TOOL", "routerku": "TOOL", "lethica": "PROJECT",
    "hermes": "TOOL", "git": "TOOL", "github": "SERVICE", "vercel": "SERVICE",
    "docker": "TOOL", "pm2": "TOOL", "pytest": "TOOL", "tomllib": "PACKAGE",
    "openai": "SERVICE", "groq": "SERVICE", "sqlalchemy": "PACKAGE",
    "fastapi": "PACKAGE", "flask": "PACKAGE", "urllib": "PACKAGE", "httpx": "PACKAGE",
}

PACKAGE_ALIASES = {
    "postgres": ["postgresql", "postgres-db", "pg"],
    "postgresdb": ["postgresql", "postgres", "pg"],
    "postgresql": ["postgres", "postgres-db", "pg"],
    "nextjs": ["next.js", "next"],
    "next.js": ["nextjs", "next"],
    "nodejs": ["node", "node.js"],
    "python3": ["python"],
}

SERVICE_TOKENS = {"database", "server", "api", "gateway", "endpoint", "queue", "broker"}
ERROR_RE = re.compile(
    r"(?i)\b(timeout|timed out|connection refused|connection reset|econnrefused|"
    r"permission denied|not found|no such file|errno\s*-?\d+|oom|out of memory|"
    r"segmentation fault|traceback|exception|crash(?:ed)?|429|403|401|402|404|500|502|504|"
    r"insufficient_balance|verification_required|rate limit)\b")
PATH_RE = re.compile(
    r"(?<![\w/.-])((?:~|/)[\w./@+-]*|[\w.-]+/[\w./@+-]+|[\w.-]+\.(?:py|js|mjs|cjs|ts|tsx|json|toml|yaml|yml|md|sh|bash|html|css|db|sqlite|env|log|txt|cfg|ini))\b")
VERSION_RE = re.compile(r"\bv?(\d+\.\d+(?:\.\d+)?)\b")
BARE_VER_RE = re.compile(r"^[\s:=~]{0,3}v?(\d+(?:\.\d+){0,2})\b")
CONFIG_RE = re.compile(r"(?i)\b(config\.toml|\.env|settings\.py|config\.py|\.gitignore|"
                       r"package\.json|requirements\.txt|[a-z_]+_config\.(?:json|toml|yaml))\b")
MSG_QUOTE = 60          # minimal panjang kutipan bukti LLM
MAX_ENTITIES = 40


# ── Phase 7: normalisasi ─────────────────────────────────────────────
def normalize_entity(name, type=None):
    """Normalisasi nama + kumpulkan alias eksplisit (bukan merge otomatis)."""
    norm = G.norm_name(name)
    aliases = []
    base = norm.replace(" ", "")
    if base in PACKAGE_ALIASES:
        aliases = list(PACKAGE_ALIASES[base])
    elif norm in PACKAGE_ALIASES:
        aliases = list(PACKAGE_ALIASES[norm])
    return {"name": norm or (name or "").strip(), "aliases": aliases[:6]}


def _fuzz(a, b):
    """Rasio kecocokan karakter sederhana (tanpa dependency eksternal)."""
    a, b = G.norm_name(a), G.norm_name(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    if a in b or b in a:
        return min(len(a), len(b)) / max(len(a), len(b))
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ── Phase 8: entity resolution ───────────────────────────────────────
def resolve(candidate, project_id=None):
    """Klasifikasi MATCH / POSSIBLE_MATCH / NEW_ENTITY / CONFLICT.

    Ambigu → POSSIBLE_MATCH (node terpisah, tautan TIDAK dibuat sampai tervalidasi).
    """
    type = candidate["type"]
    name = candidate["name"]
    norm, aliases = normalize_entity(name), None
    norm = norm["name"]
    aliases = normalize_entity(name)["aliases"]
    pid = project_id if candidate.get("scope") == "PROJECT" else project_id
    exact = None
    for n in G._nodes():
        if n["type"] != type:
            continue
        nnames = [G.norm_name(n["name"])] + [G.norm_name(a) for a in (n.get("properties", {}).get("aliases") or [])]
        if norm in nnames:
            if (n.get("project_id") or None) == (pid or None):
                exact = n
                break
            if n.get("scope") == "GLOBAL" and candidate.get("scope") != "PROJECT":
                exact = n
                break
            if exact is None:
                exact = n        # match beda project → POSSIBLE
    if exact:
        same_project = (exact.get("project_id") or None) == (pid or None)
        if not same_project:
            return {"verdict": "POSSIBLE_MATCH", "node": exact,
                    "reason": "same name+type in different project scope — not merged"}
        new_ver = candidate.get("version")
        old_ver = exact.get("version")
        if (new_ver and old_ver and new_ver != old_ver
                and exact.get("status") in ("CURRENT", "ACTIVE")
                and candidate.get("source") == "EXECUTION_EVIDENCE"
                and exact.get("source") == "EXECUTION_EVIDENCE"):
            return {"verdict": "CONFLICT", "node": exact,
                    "reason": f"current version {old_ver} vs new evidence {new_ver}"}
        return {"verdict": "MATCH", "node": exact}
    # fuzzy terhadap type+project sama
    for n in G._nodes():
        if n["type"] != type or (n.get("project_id") or None) != (pid or None):
            continue
        if _fuzz(n["name"], norm) >= 0.85:
            return {"verdict": "POSSIBLE_MATCH", "node": n,
                    "reason": f"fuzzy {_fuzz(n['name'], norm):.2f} — not auto-merged"}
    return {"verdict": "NEW_ENTITY", "node": None}


def ensure_node(candidate, project_id=None, task=None):
    """Resolve → create kalau perlu. Return (node, verdict)."""
    verd = resolve(candidate, project_id)
    v = verd["verdict"]
    if v == "MATCH":
        G.obs_inc("entities_resolved")
        return verd["node"], v
    if v == "POSSIBLE_MATCH":
        G.obs_inc("entities_unresolved")
    cand = dict(candidate)
    aliases = normalize_entity(cand["name"])["aliases"]
    props = dict(cand.get("properties") or {})
    if aliases:
        props["aliases"] = sorted(set((props.get("aliases") or []) + aliases))[:10]
    if v == "POSSIBLE_MATCH" and verd.get("node"):
        props["possible_match"] = verd["node"]["id"]
        props["possible_match_reason"] = verd.get("reason")
    scope = cand.get("scope") or ("PROJECT" if project_id else "GLOBAL")
    res = G.add_node(cand["type"], cand["name"], cand.get("description", ""),
                     properties=props, source=cand.get("source", "EXECUTION_EVIDENCE"),
                     confidence=cand.get("confidence"), project_id=project_id if scope == "PROJECT" else None,
                     scope=scope, version=cand.get("version"))
    if v == "CONFLICT" and verd.get("node"):
        G.mark_conflict(verd["node"]["id"], reason=verd.get("reason"),
                        other_id=res["node"]["id"])
    return res["node"], v


# ── Phase 6: entity extraction (deterministik) ───────────────────────
def extract_deterministic(text, project_id=None):
    """Ambil entity + relasi yang benar-benar disebut teks. Semua ber-evidence quote."""
    text = text or ""
    low = text.lower()
    out = []
    seen = set()

    def push(type, name, quote, props=None, source="EXECUTION_EVIDENCE", version=None):
        key = (type, G.norm_name(name))
        if key in seen or len(out) >= MAX_ENTITIES:
            return
        seen.add(key)
        out.append({"type": type, "name": name, "description": quote[:300],
                    "properties": {**(props or {}), "evidence": [quote[:200]]},
                    "source": source, "version": version,
                    "scope": "PROJECT" if project_id else "GLOBAL"})

    # paket / service / tool / environment
    pkg_hit = set()
    for token, ntype in PACKAGE_LEX.items():
        m = re.search(r"(?<![a-z0-9])" + re.escape(token) + r"(?![a-z0-9])", low)
        if not m:
            continue
        pkg_hit.add(G.norm_name(token))
        pkg_hit.update(G.norm_name(a) for a in PACKAGE_ALIASES.get(token, []))
        quote = text[max(0, m.start() - 40):m.end() + 40].strip()
        ver = None
        tail = text[m.end():m.end() + 20]
        head = text[max(0, m.start() - 20):m.start()]
        for src in (tail,):
            vm = BARE_VER_RE.match(src) or VERSION_RE.search(src)
            if vm:
                ver = vm.group(1)
                break
        if not ver:
            vm = VERSION_RE.search(head) or re.search(r"v?(\d+(?:\.\d+){0,2})\s*$", head)
            if vm:
                ver = vm.group(1)
        push(ntype, token, quote, version=ver)
    # buang token package yang sebenarnya alias dari token lain yang sudah tertangkap
    # (mis. "next" saat "next.js" juga ada) — hindari node kembar, BUKAN merge otomatis
    pkgs = [c for c in out if c["type"] in ("PACKAGE", "SERVICE", "TOOL", "ENVIRONMENT")
            and G.norm_name(c["name"]) in pkg_hit]
    groups = []
    for c in pkgs:
        nn = G.norm_name(c["name"])
        grp = {nn} | {G.norm_name(a) for a in PACKAGE_ALIASES.get(nn, [])}
        merged = False
        for g in groups:
            if g & grp:
                g |= grp
                merged = True
                break
        if not merged:
            groups.append(set(grp))
    drop = set()
    for g in groups:
        members = [c for c in pkgs if G.norm_name(c["name"]) in g]
        if len(members) < 2:
            continue
        keep_name = max(members, key=lambda c: len(G.norm_name(c["name"])))
        # bias kanonik: nama yang punya entry alias = bentuk panjang/kanonik
        canon = [c for c in members if G.norm_name(c["name"]) in PACKAGE_ALIASES]
        if canon:
            keep_name = max(canon, key=lambda c: len(c["name"]))
        for c in members:
            if c is not keep_name:
                drop.add((c["type"], G.norm_name(c["name"])))
    out = [c for c in out if (c["type"], G.norm_name(c["name"])) not in drop]

    # file / directory
    for m in PATH_RE.finditer(text):
        p = m.group(1)
        if len(p) < 4 or p.startswith("http"):
            continue
        if G.norm_name(p) in pkg_hit:
            continue  # "Next.js" bukan file
        quote = text[max(0, m.start() - 40):m.end() + 40].strip()
        is_dir = p.endswith("/")
        push("DIRECTORY" if is_dir else "FILE", p, quote,
             props={"path": p, "basename": os.path.basename(p.rstrip("/"))})

    # konfigurasi
    for m in CONFIG_RE.finditer(text):
        quote = text[max(0, m.start() - 40):m.end() + 40].strip()
        push("CONFIGURATION", m.group(1), quote, props={"path": m.group(1)})

    # error / failure signal
    for m in ERROR_RE.finditer(text):
        quote = text[max(0, m.start() - 50):m.end() + 50].strip()
        push("ERROR", m.group(1).lower(), quote, source="EXECUTION_EVIDENCE")

    return out


def extract_llm(task):
    """Ekstraksi LLM OPSIONAL. Setiap relasi wajib punya kutipan bukti yang ADA di teks."""
    client = getattr(task, "client", None)
    text = _task_text(task)
    if client is None or not text.strip():
        return {"entities": [], "relations": [], "dropped": 0}
    prompt = (
        "Ekstrak entity & relasi DARI TEKS. Balas HANYA JSON: "
        '{"entities":[{"type":str,"name":str,"evidence":str}],'
        '"relations":[{"source":str,"relation":str,"target":str,"evidence":str,"why":str}]}. '
        f"type valid: {', '.join(sorted(G.NODE_TYPES))}. "
        f"relation valid: {', '.join(sorted(G.RELATION_TYPES))}. "
        "ATURAN KERAS: field evidence HARUS kutipan PERSIS dari teks (>=25 karakter). "
        "DILARANG menyimpulkan kausalitas dari korelasi. DILARANG mengarang. "
        "Max 12 entity & 12 relasi.")
    try:
        from core import orchestra
        data = orchestra._ask_json(task, prompt, text[:4000], max_tokens=1200)
    except Exception:
        data = None
    if not isinstance(data, dict):
        return {"entities": [], "relations": [], "dropped": 0}
    G.obs_inc("llm_extractions")
    dropped = 0
    low = text.lower()
    ents = []
    for e in (data.get("entities") or [])[:12]:
        if not isinstance(e, dict):
            continue
        if e.get("type") not in G.NODE_TYPES or not e.get("name"):
            dropped += 1
            continue
        quote = str(e.get("evidence") or "")
        if len(quote.strip()) < MSG_QUOTE or quote.strip().lower()[:40] not in low:
            dropped += 1
            continue
        ents.append({"type": e["type"], "name": str(e["name"])[:120],
                     "description": quote[:300],
                     "properties": {"evidence": [quote[:200]]},
                     "source": "LETHICA_INFERENCE", "scope": None,
                     "_quote": quote})
    rels = []
    for r in (data.get("relations") or [])[:12]:
        if not isinstance(r, dict):
            continue
        quote = str(r.get("evidence") or "")
        if (r.get("relation") not in G.RELATION_TYPES or not r.get("source")
                or not r.get("target") or len(quote.strip()) < MSG_QUOTE
                or quote.strip().lower()[:40] not in low):
            dropped += 1
            continue
        rels.append({"source": str(r["source"])[:120], "relation": r["relation"],
                     "target": str(r["target"])[:120],
                     "properties": {"evidence": [quote[:200]], "why": str(r.get("why") or "")[:200]},
                     "source_type": "LETHICA_INFERENCE"})
    return {"entities": ents, "relations": rels, "dropped": dropped}


def _task_text(task):
    parts = [getattr(task, "goal", "") or ""]
    plan = getattr(task, "plan", None) or {}
    for st in plan.get("subtasks", []) or []:
        parts.append(str(st.get("description") or ""))
    for r in (getattr(task, "subtask_results", {}) or {}).values():
        if isinstance(r, dict):
            parts.append(str(r.get("result") or "")[:600])
            for a in (r.get("actions") or [])[:10]:
                parts.append(str(a)[:300])
    for f in getattr(task, "failure_patterns", []) or []:
        parts.append(f"{f.get('failure_type')} {f.get('root_cause')} {f.get('fix')}")
    for d in getattr(task, "debug_log", []) or []:
        parts.append(f"{d.get('root_cause')} {d.get('fix_steps')}")
    parts.append(getattr(task, "final_solution", "") or "")
    return "\n".join(p for p in parts if p)


# ── Phase 24/25/16/17/18/19: sink task → graph ───────────────────────
def record_task(task, use_llm=True):
    """Bangun/update graph dari task nyata. Bukti = tool action & hasil eksekusi.

    Return trace dict (jumlah node/edge + verdict). Non-fatal: caller wajib try/except.
    """
    goal = getattr(task, "goal", "") or ""
    project_id = getattr(task, "project_id", None)
    trace = {"nodes": 0, "edges": 0, "entities": {}, "dropped": 0, "conflicts": 0,
             "relations": []}
    text = _task_text(task)

    # 1) PROJECT + TASK nodes
    proj_node = None
    if project_id:
        proj_node, _ = ensure_node({"type": "PROJECT", "name": project_id, "scope": "PROJECT",
                                    "source": "EXECUTION_EVIDENCE",
                                    "description": f"project {project_id}"}, project_id, task)
        trace["nodes"] += 1
    task_node, _ = ensure_node({"type": "TASK", "name": goal[:120], "source": "EXECUTION_EVIDENCE",
                               "description": goal[:400], "scope": "PROJECT" if project_id else "GLOBAL"},
                              project_id, task)
    trace["nodes"] += 1
    if proj_node:
        G.add_edge(proj_node["id"], "CONTAINS", task_node["id"], source="EXECUTION_EVIDENCE",
                   properties={"evidence": [goal[:200]]})
        trace["edges"] += 1

    # 2) entity deterministik
    cands = extract_deterministic(text, project_id)
    llm = extract_llm(task) if use_llm else {"entities": [], "relations": [], "dropped": 0}
    trace["dropped"] = llm.get("dropped", 0)
    by_name = {}
    for c in cands + [e for e in llm["entities"]]:
        if c.get("scope") is None:
            c["scope"] = "PROJECT" if project_id else "GLOBAL"
        node, verdict = ensure_node(c, project_id, task)
        trace["entities"][G.norm_name(c["name"])] = verdict
        trace["nodes"] += 1
        by_name[G.norm_name(c["name"])] = node
        if verdict == "CONFLICT":
            trace["conflicts"] += 1
        # relasi task→entity (evidence nyata: disebut dalam task)
        rel = {"ERROR": "FAILS_WITH", "FAILURE": "FAILED_WITH", "SOLUTION": "PRODUCES"}.get(c["type"], "USES")
        r = G.add_edge(task_node["id"], rel, node["id"], source=c.get("source", "EXECUTION_EVIDENCE"),
                       properties={"evidence": c.get("properties", {}).get("evidence", [])})
        if r.get("ok"):
            trace["edges"] += 1
            trace["relations"].append(f"TASK {rel} {c['type']}:{c['name']}")
        if proj_node and c.get("type") in ("PACKAGE", "SERVICE", "TOOL", "ENVIRONMENT",
                                           "CONFIGURATION", "FILE", "DIRECTORY", "API"):
            r2 = G.add_edge(proj_node["id"], "USES", node["id"],
                            source=c.get("source", "EXECUTION_EVIDENCE"),
                            properties={"evidence": c.get("properties", {}).get("evidence", [])})
            if r2.get("ok"):
                trace["edges"] += 1
            if c["type"] == "FILE" and project_id:
                r3 = G.add_edge(proj_node["id"], "CONTAINS", node["id"], source="EXECUTION_EVIDENCE",
                                properties={"evidence": c.get("properties", {}).get("evidence", [])})
                if r3.get("ok"):
                    trace["edges"] += 1

    # 3) relasi LLM (sudah lolos guard kutipan bukti)
    for r in llm["relations"]:
        s = by_name.get(G.norm_name(r["source"])) or G.find_by_name(r["source"])
        t = by_name.get(G.norm_name(r["target"])) or G.find_by_name(r["target"])
        if not s or not t:
            continue
        res = G.add_edge(s["id"], r["relation"], t["id"], properties=r["properties"],
                         source="LETHICA_INFERENCE")
        if res.get("ok"):
            trace["edges"] += 1
            trace["relations"].append(f"{r['source']} {r['relation']} {r['target']}")

    # 4) failure/solution dari debug_log — kausal HANYA kalau ada root_cause eksplisit
    for d in getattr(task, "debug_log", []) or []:
        rc = str(d.get("root_cause") or "").strip()
        if not rc:
            continue
        fail_node, _ = ensure_node({"type": "FAILURE", "name": rc[:120], "scope":
                                    "PROJECT" if project_id else "GLOBAL",
                                    "source": "EXECUTION_EVIDENCE", "description": rc[:300]}, project_id, task)
        G.add_edge(task_node["id"], "FAILED_WITH", fail_node["id"], source="EXECUTION_EVIDENCE",
                   properties={"evidence": [rc[:200]]})
        trace["nodes"] += 1
        trace["edges"] += 1
        for err in (d.get("errors") or [])[:3]:
            en = G.find_by_name(str(err)[:120], type="ERROR")
            if en:
                G.add_edge(fail_node["id"], "CAUSED_BY", en["id"], source="EXECUTION_EVIDENCE",
                           properties={"evidence": [f"root cause explicitly stated: {rc[:150]}"]})
                trace["edges"] += 1
        for fix in ([d.get("fix_steps")] if isinstance(d.get("fix_steps"), str) else (d.get("fix_steps") or []))[:3]:
            fx = str(fix).strip()
            if not fx:
                continue
            sol, _ = ensure_node({"type": "SOLUTION", "name": fx[:120], "scope":
                                  "PROJECT" if project_id else "GLOBAL",
                                  "source": "EXECUTION_EVIDENCE", "description": fx[:300]}, project_id, task)
            G.add_edge(fail_node["id"], "SOLVED_BY", sol["id"], source="EXECUTION_EVIDENCE",
                       properties={"evidence": [f"explicit repair step: {fx[:150]}"]})
            G.add_edge(task_node["id"], "VALIDATED_BY", sol["id"], source="EXECUTION_EVIDENCE",
                       properties={"evidence": ["repair applied during task"]})
            trace["nodes"] += 1
            trace["edges"] += 2

    # 5) skill & strategy (Phase 18/19) — evidence: dipakai task ini
    sr = getattr(task, "skill_report", None) or {}
    for sk in (sr.get("available_skills") or [])[:6]:
        sn, _ = ensure_node({"type": "SKILL", "name": str(sk), "scope": "SKILL",
                             "source": "EXECUTION_EVIDENCE",
                             "description": f"skill used by task {task.id}"}, None, task)
        G.add_edge(task_node["id"], "USES", sn["id"], source="EXECUTION_EVIDENCE",
                   properties={"evidence": [f"skill_report listed '{sk}'"]})
        trace["edges"] += 1
        trace["nodes"] += 1
    strat = getattr(task, "strategy", None)
    if strat is not None:
        sid = getattr(strat, "id", None) or str(strat)
        stn, _ = ensure_node({"type": "STRATEGY", "name": str(sid), "scope": "STRATEGY",
                              "source": "EXECUTION_EVIDENCE",
                              "description": getattr(strat, "description", "") or str(sid)}, None, task)
        ok = getattr(task, "state", "") == "COMPLETED"
        G.add_edge(task_node["id"], "USES", stn["id"], source="EXECUTION_EVIDENCE",
                   properties={"evidence": [f"strategy '{sid}' selected for task"]})
        G.add_edge(stn["id"], "SUCCEEDED_IN" if ok else "FAILS_WITH", task_node["id"],
                   source="EXECUTION_EVIDENCE",
                   properties={"evidence": [f"task state={getattr(task,'state','')}"]})
        trace["edges"] += 2
        trace["nodes"] += 1

    # 6) status akhir task → world model update
    status = "CURRENT" if getattr(task, "state", "") == "COMPLETED" else "STALE"
    G.update_node(task_node["id"], {"status": status})
    G.obs_inc("world_model_updates")
    return trace


# ── Phase 28: impact analysis ────────────────────────────────────────
def impact_analysis(node_id, max_depth=2, max_nodes=50):
    """Node yang berpotensi terdampak kalau node ini berubah. Bukti arah, bukan tebakan."""
    sg = G.subgraph(node_id, max_depth=max_depth, max_nodes=max_nodes)
    G.obs_inc("impact_analysis_count")
    affected = [n for n in sg["nodes"] if n["id"] != node_id]
    def of_type(t):
        return [n["name"] for n in affected if n["type"] == t]
    return {"root": (sg["root"] or {}).get("name"), "affected_nodes": len(affected),
            "affected_skills": of_type("SKILL"), "affected_strategies": of_type("STRATEGY"),
            "affected_projects": of_type("PROJECT"), "affected_files": of_type("FILE"),
            "depth_reached": sg["depth_reached"], "truncated": sg.get("truncated", False)}


# ── Phase 31: research → SOURCE + SUPPORTS ───────────────────────────
def record_research(query, results, project_id=None, task_id=None):
    """Hasil riset = SOURCE node (LOW confidence) + edge SUPPORTS ke FACT/SOLUTION.
    Bukan kebenaran permanen: confidence LOW + source WEB_EVIDENCE."""
    trace = {"sources": 0, "supports": 0}
    for r in (results or [])[:8]:
        url = str(r.get("url") or r.get("link") or "").strip()
        title = str(r.get("title") or r.get("name") or url or query)[:160]
        if not url and not title:
            continue
        sn, _ = ensure_node({"type": "SOURCE", "name": title or url, "scope": "GLOBAL",
                             "source": "WEB_EVIDENCE", "confidence": "LOW",
                             "description": str(r.get("snippet") or r.get("description") or "")[:400],
                             "properties": {"url": url, "query": query, "task_id": task_id}}, None, None)
        trace["sources"] += 1
        fact_text = str(r.get("snippet") or r.get("description") or title)[:300]
        if fact_text:
            fn, _ = ensure_node({"type": "FACT", "name": fact_text[:120], "scope": "GLOBAL",
                                 "source": "WEB_EVIDENCE", "confidence": "LOW",
                                 "description": fact_text}, None, None)
            res = G.add_edge(sn["id"], "SUPPORTS", fn["id"], source="WEB_EVIDENCE",
                             properties={"evidence": [f"{url} :: {fact_text[:120]}"]})
            if res.get("ok"):
                trace["supports"] += 1
    return trace


# ── Phase 20: decision memory ────────────────────────────────────────
def record_decision(decision, reason, project_id=None, evidence=None, task_id=None):
    """Keputusan penting → DECISION node (mencegah reconsideration berulang)."""
    if not decision:
        return {"ok": False, "reason": "empty decision"}
    node, verdict = ensure_node({"type": "DECISION", "name": str(decision)[:120],
                                 "description": f"{decision}. Reason: {reason}",
                                 "scope": "PROJECT" if project_id else "GLOBAL",
                                 "source": "USER_INPUT", "confidence": "MEDIUM",
                                 "properties": {"reason": str(reason or "")[:300],
                                                "evidence": evidence or [],
                                                "task_id": task_id}},
                                project_id, None)
    if project_id:
        p, _ = ensure_node({"type": "PROJECT", "name": project_id, "scope": "PROJECT",
                            "source": "EXECUTION_EVIDENCE"}, project_id, None)
        G.add_edge(p["id"], "CONTAINS", node["id"], source="USER_INPUT",
                   properties={"evidence": ["decision made in project context"]})
    return {"ok": True, "node": node, "verdict": verdict}


# ── Phase 18/30: skill & strategy graph hooks ────────────────────────
def link_skill_version(skill_name, version, parent_version=None, status="ACTIVE",
                       evidence=None):
    sk, _ = ensure_node({"type": "SKILL", "name": skill_name, "scope": "SKILL",
                         "source": "EXECUTION_EVIDENCE",
                         "description": f"skill {skill_name}"}, None, None)
    sv, _ = ensure_node({"type": "SKILL_VERSION", "name": f"{skill_name} {version}",
                         "scope": "SKILL", "source": "EXECUTION_EVIDENCE", "version": version,
                         "status": status,
                         "description": f"skill {skill_name} version {version}"}, None, None)
    G.add_edge(sk["id"], "HAS_VERSION", sv["id"], source="EXECUTION_EVIDENCE",
               properties={"evidence": evidence or [f"evolution produced {version}"]})
    if parent_version:
        pv = G.find_by_name(f"{skill_name} {parent_version}", type="SKILL_VERSION")
        if not pv:
            # Historical version belum pernah tercatat → buat node dulu (status
            # HISTORICAL). SUPERSEDES butuh target nyata; jangan biarkan edge
            # references versi lama yang tidak ada (test 19/29 gagal karenanya).
            pv, _ = ensure_node({"type": "SKILL_VERSION",
                                 "name": f"{skill_name} {parent_version}",
                                 "scope": "SKILL", "source": "EXECUTION_EVIDENCE",
                                 "version": str(parent_version), "status": "HISTORICAL",
                                 "freshness": "STALE",
                                 "description": f"skill {skill_name} version {parent_version} "
                                                f"(historical)"}, None, None)
        if pv:
            G.add_edge(sv["id"], "SUPERSEDES", pv["id"], source="EXECUTION_EVIDENCE",
                       properties={"evidence": [f"{version} supersedes {parent_version}"]})
            G.update_node(pv["id"], {"status": "HISTORICAL", "freshness": "STALE"})
    return {"skill": sk["id"], "version": sv["id"]}


def link_strategy_outcome(strategy_id, task_id, success, evidence=None):
    # Ensure node dulu — sink boleh dipanggil sebelum task graph dibangun
    # (test 30): jangan return ok:False cuma karena node belum ada.
    stn = G.find_by_name(strategy_id, type="STRATEGY")
    if not stn:
        stn, _ = ensure_node({"type": "STRATEGY", "name": str(strategy_id),
                              "scope": "STRATEGY", "source": "EXECUTION_EVIDENCE",
                              "description": f"strategy {strategy_id}"}, None, None)
    tk = G.find_by_name(str(task_id), type="TASK")
    if not tk:
        tk, _ = ensure_node({"type": "TASK", "name": str(task_id),
                             "scope": "GLOBAL", "source": "EXECUTION_EVIDENCE",
                             "description": f"task {task_id}"}, None, None)
    if not stn or not tk:
        return {"ok": False, "reason": "strategy or task node could not be ensured"}
    r = G.add_edge(stn["id"], "SUCCEEDED_IN" if success else "FAILS_WITH", tk["id"],
                   source="EXECUTION_EVIDENCE",
                   properties={"evidence": evidence or ["strategy outcome recorded"]})
    return {"ok": r.get("ok"), "edge": r.get("edge")}


def record_memory_link(memory, node_name=None):
    """Phase 12: MEMORY node ↔ entity yang disebut memori (evidence: entity list memori)."""
    ents = [e for e in (memory.get("entities") or []) if e][:6]
    if not ents and node_name:
        ents = [node_name]
    if not ents:
        return {"ok": False, "reason": "no entities"}
    mn, _ = ensure_node({"type": "MEMORY", "name": f"mem {memory.get('id')}", "scope": memory.get("scope", "GLOBAL"),
                         "source": memory.get("source", "LETHICA_INFERENCE"),
                         "description": (memory.get("title") or "")[:200],
                         "properties": {"memory_id": memory.get("id")}}, None, None)
    linked = 0
    for e in ents:
        en = G.find_by_name(str(e))
        if not en:
            en, _ = ensure_node({"type": "FACT", "name": str(e)[:120], "scope": "GLOBAL",
                                 "source": "LETHICA_INFERENCE", "description": str(e)[:200]}, None, None)
        r = G.add_edge(mn["id"], "RELATED_TO", en["id"], source="LETHICA_INFERENCE",
                       properties={"evidence": [f"memory {memory.get('id')} entity list"]})
        linked += int(bool(r.get("ok")))
    return {"ok": linked > 0, "linked": linked}


if __name__ == "__main__":
    print(G.summary())