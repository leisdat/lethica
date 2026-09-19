# core/world.py — v3.6.0 World Model (structured belief about projects/systems)
#
# "Apa yang Lethica saat ini percaya tentang project ini?" — dihitung dari Knowledge Graph,
# TANPA menyimpan duplikat state (single source of truth = graph nodes/edges).
#
# High-level queries (Phase 27) menyembunyikan detail graph:
#   get_project_state get_dependencies get_known_failures get_known_solutions
#   get_recent_changes get_related_skills get_related_strategies get_current_versions
#   get_problem_history get_change_impact get_decisions
#
# Prinsip: freshness eksplisit (CURRENT/STALE/UNKNOWN/CONFLICTED), historical state TIDAK
# dihapus, scope project tidak bocor, dan tidak ada relasi yang dikarang.
from core import graph as G

WM_TYPES = ("PROJECT", "SERVICE", "API", "PACKAGE", "DEPENDENCY", "TOOL",
            "ENVIRONMENT", "CONFIGURATION", "FILE", "DIRECTORY", "SKILL", "STRATEGY")


def _project_node(project_id):
    if not project_id:
        return None
    return G.find_by_name(project_id, type="PROJECT")


def _ensure_project(project_id):
    n = _project_node(project_id)
    if n:
        return n
    res = G.add_node("PROJECT", project_id, project_id=project_id, scope="PROJECT",
                     source="EXECUTION_EVIDENCE", description=f"project {project_id}")
    return res.get("node")


def _by_edge(node_id, relation, direction="out", limit=50, types=None):
    """Ambil node lewat relation tertentu (bukti relasi eksplisit)."""
    out = []
    for e in G.get_edges(node_id, direction=direction):
        if e["relation"] != relation:
            continue
        other_id = e["target_node"] if e["source_node"] == node_id else e["source_node"]
        n = G.get_node(other_id)
        if not n:
            continue
        if types and n["type"] not in types:
            continue
        out.append({"node": n, "edge": e})
        if len(out) >= limit:
            break
    return out


def get_project_state(project_id, include_global=True):
    """Phase 9: ringkasan state project + freshness eksplisit."""
    G.obs_inc("world_queries", "graph_queries")
    p = _ensure_project(project_id)
    if not p:
        return {"project": project_id, "found": False, "status": "UNKNOWN",
                "freshness": "UNKNOWN", "nodes": 0}
    comp = _by_edge(p["id"], "USES", types=WM_TYPES) + _by_edge(p["id"], "CONTAINS")
    # node yang menyatakan dirinya PART_OF/CONTAINED project (bukti relasi eksplisit)
    for e in G.get_edges(p["id"], direction="in"):
        if e["relation"] not in ("PART_OF", "USED_IN", "DEPLOYED_TO", "OCCURRED_IN"):
            continue
        n = G.get_node(e["source_node"])
        if n:
            comp.append({"node": n, "edge": e})
    # node scope=PROJECT yang belum punya edge eksplisit ke project (dibuat via
    # ensure_node/add_node project_id=...): tetap bagian dari world model project
    # (test H: uvicorn ber-project_id tapi tanpa edge ProjectB→uvicorn).
    seen_ids = {c["node"]["id"] for c in comp}
    for n in G.scoped_nodes(project_id, include_global=False):
        if n["id"] not in seen_ids and n["id"] != p["id"]:
            comp.append({"node": n, "edge": None})
            seen_ids.add(n["id"])
    # failure/solution/decision yang menempel ke task dalam project ini
    # v3.6.1: kumpulkan dari SEMUA komponen (API→FAILS_WITH, SERVICE→PRODUCES, dll),
    # bukan hanya TASK — world model harus melihat failure nyata (test 24).
    for c in list(comp):
        for e in G.get_edges(c["node"]["id"], direction="out"):
            if e["relation"] not in ("FAILED_WITH", "FAILS_WITH", "PRODUCES"):
                continue
            n2 = G.get_node(e["target_node"])
            if n2 and n2["type"] in ("FAILURE", "SOLUTION"):
                comp.append({"node": n2, "edge": e})
    kinds = {}
    for c in comp:
        kinds.setdefault(c["node"]["type"], []).append(c["node"]["name"])
    stale = [c["node"]["name"] for c in comp if c["node"].get("freshness") == "STALE"]
    conf = [c["node"]["name"] for c in comp if c["node"].get("status") == "CONFLICTED"]
    return {"project": p["name"], "found": True, "status": p.get("status"),
            "freshness": p.get("freshness"), "last_verified": p.get("last_verified"),
            "nodes": len(comp), "components": kinds,
            "dependencies": kinds.get("PACKAGE", []) + kinds.get("DEPENDENCY", []),
            "services": kinds.get("SERVICE", []), "apis": kinds.get("API", []),
            "files": kinds.get("FILE", []), "configs": kinds.get("CONFIGURATION", []),
            "stale": stale, "conflicted": conf}


def get_dependencies(project_id, transitive=False, max_depth=2):
    """Phase 26: dependency graph (project → package → package)."""
    G.obs_inc("world_queries")
    p = _project_node(project_id)
    if not p:
        return {"project": project_id, "dependencies": []}
    direct = [c["node"]["name"] for c in
              _by_edge(p["id"], "USES", types=("PACKAGE", "DEPENDENCY", "SERVICE", "TOOL"))]
    direct += [c["node"]["name"] for c in _by_edge(p["id"], "DEPENDS_ON")]
    out = {"project": project_id, "dependencies": direct, "transitive": []}
    if transitive:
        for d in direct:
            n = G.find_by_name(d, type="PACKAGE") or G.find_by_name(d, type="DEPENDENCY")
            if not n:
                continue
            sub = G.subgraph(n["id"], max_depth=max_depth, max_nodes=20,
                             allowed_relations={"DEPENDS_ON", "USES"})
            out["transitive"].extend(x["name"] for x in sub["nodes"] if x["id"] != n["id"])
    return out


def get_known_failures(project_id=None, limit=20):
    G.obs_inc("world_queries")
    out = []
    for n in G.scoped_nodes(project_id) if project_id else G._nodes():
        if n["type"] != "FAILURE":
            continue
        causes = [c["node"]["name"] for c in _by_edge(n["id"], "CAUSED_BY")]
        fix = [c["node"]["name"] for c in _by_edge(n["id"], "SOLVED_BY")]
        out.append({"failure": n["name"], "confidence": n.get("confidence"),
                    "freshness": n.get("freshness"),
                    "explicit_causes": causes, "known_fixes": fix,
                    "note": "causes listed only if explicitly stated in evidence"})
    return {"project": project_id, "failures": out[:limit], "count": len(out)}


def get_known_solutions(project_id=None, limit=20):
    G.obs_inc("world_queries")
    out = []
    for n in G.scoped_nodes(project_id) if project_id else G._nodes():
        if n["type"] != "SOLUTION":
            continue
        used_in = [e["source_node"] for e in G.get_edges(n["id"], direction="in")
                   if e["relation"] in ("SOLVED_BY", "VALIDATED_BY")]
        tasks = []
        for tid in used_in:
            t = G.get_node(tid)
            if t and t["type"] == "TASK":
                tasks.append(t["name"][:80])
        out.append({"solution": n["name"], "confidence": n.get("confidence"),
                    "freshness": n.get("freshness"), "evidence": n.get("properties", {}).get("evidence"),
                    "validated_in_tasks": tasks[:5]})
    return {"project": project_id, "solutions": out[:limit], "count": len(out)}


def get_recent_changes(project_id=None, limit=20, since_ts=None):
    G.obs_inc("world_queries")
    nodes = [n for n in G._nodes() if n.get("updated_at")]
    if since_ts:
        nodes = [n for n in nodes if G._ts(n["updated_at"]) >= since_ts]
    if project_id:
        vis = {n["id"] for n in G.scoped_nodes(project_id)}
        nodes = [n for n in nodes if n["id"] in vis]
    nodes.sort(key=lambda n: G._ts(n["updated_at"]), reverse=True)
    return {"project": project_id,
            "changes": [{"node": n["name"], "type": n["type"], "at": n["updated_at"],
                         "status": n.get("status")} for n in nodes[:limit]]}


def get_related_skills(node_id=None, project_id=None, limit=20):
    G.obs_inc("world_queries")
    out = []
    seen = set()
    roots = []
    if node_id:
        roots.append(node_id)
    if project_id:
        p = _project_node(project_id)
        if p:
            roots.append(p["id"])
    for r in roots:
        sg = G.subgraph(r, max_depth=2, max_nodes=40)
        for n in sg["nodes"]:
            if n["type"] == "SKILL" and n["id"] not in seen:
                seen.add(n["id"])
                out.append(n["name"])
    return {"skills": out[:limit], "count": len(out)}


def get_related_strategies(project_id=None, limit=20):
    G.obs_inc("world_queries")
    p = _project_node(project_id) if project_id else None
    out, seen = [], set()
    for n in G._nodes():
        if n["type"] != "STRATEGY":
            continue
        if p:
            sg = G.subgraph(p["id"], max_depth=3, max_nodes=60)
            if not any(x["id"] == n["id"] for x in sg["nodes"]):
                continue
        if n["id"] in seen:
            continue
        seen.add(n["id"])
        outs = G.get_edges(n["id"], direction="out")
        succ = sum(1 for e in outs if e["relation"] == "SUCCEEDED_IN")
        fail = sum(1 for e in outs if e["relation"] == "FAILS_WITH")
        out.append({"strategy": n["name"], "success_edges": succ, "failure_edges": fail,
                    "confidence": n.get("confidence")})
    return {"strategies": out[:limit], "count": len(out)}


def get_current_versions(name=None, project_id=None):
    """Phase 10/32: versi CURRENT sekarang — historical tetap tersimpan terpisah."""
    G.obs_inc("world_queries")
    out = []
    for n in G._nodes():
        if not n.get("version"):
            continue
        if name and G.norm_name(name) not in G.norm_name(n["name"]):
            continue
        if project_id and n.get("scope") == "PROJECT" and n.get("project_id") != project_id:
            continue
        hist = [h.get("state", {}).get("version") for h in (n.get("history") or [])
                if h.get("state", {}).get("version")]
        out.append({"node": n["name"], "type": n["type"], "current_version": n["version"],
                    "historical_versions": hist, "freshness": n.get("freshness"),
                    "status": n.get("status"), "last_verified": n.get("last_verified")})
    return {"versions": out}


def get_problem_history(problem_query, project_id=None, limit=10):
    """Riwayat masalah serupa + solusi yang pernah dipakai (evidence-based)."""
    G.obs_inc("world_queries")
    hits = G.search(problem_query, limit=limit * 2)
    out = []
    for n in hits:
        if n["type"] not in ("FAILURE", "ERROR"):
            continue
        if project_id and n.get("scope") == "PROJECT" and n.get("project_id") != project_id:
            continue
        out.append({"problem": n["name"], "type": n["type"],
                    "known_fixes": [c["node"]["name"] for c in _by_edge(n["id"], "SOLVED_BY")],
                    "freshness": n.get("freshness"), "confidence": n.get("confidence")})
        if len(out) >= limit:
            break
    return {"query": problem_query, "history": out}


def get_change_impact(node_id=None, name=None, type=None, max_depth=2):
    """Phase 28: node berpotensi terdampak kalau komponen ini berubah."""
    from core import capture
    n = G.get_node(node_id) if node_id else G.find_by_name(name, type=type)
    if not n:
        return {"found": False, "affected_nodes": 0}
    res = capture.impact_analysis(n["id"], max_depth=max_depth)
    res["found"] = True
    res["node"] = n["name"]
    return res


def get_decisions(project_id=None, limit=20):
    G.obs_inc("world_queries")
    out = []
    for n in G.scoped_nodes(project_id) if project_id else G._nodes():
        if n["type"] != "DECISION":
            continue
        out.append({"decision": n["name"], "reason": n.get("properties", {}).get("reason"),
                    "at": n.get("created_at"), "evidence": n.get("properties", {}).get("evidence")})
    return {"decisions": out[:limit], "count": len(out)}


def summary(project_id=None):
    if project_id:
        st = get_project_state(project_id)
        return (f"World Model [{project_id}]: status={st.get('status')} freshness={st.get('freshness')} "
                f"components={st.get('nodes')} stale={len(st.get('stale') or [])} "
                f"conflicted={len(st.get('conflicted') or [])}")
    return G.summary()


def refresh(stale_days=30):
    """Phase 32: reklasifikasi freshness seluruh graph + tandai edge kedaluwarsa."""
    G.obs_inc("world_model_updates")
    res = G.refresh_freshness(stale_days=stale_days)
    expired = []
    import time as _t
    for e in G._edges():
        if e.get("valid_until") and G._ts(e["valid_until"]) < _t.time() and e.get("status") != "STALE":
            expired.append(e["id"])
    if expired:
        G.mark_stale(edge_ids=expired)
    res["expired_edges"] = len(expired)
    return res


if __name__ == "__main__":
    print(summary())