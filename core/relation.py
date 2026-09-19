# core/relation.py — v3.6.0 relationship-aware retrieval (semantic + graph)
#
# Menyatukan v3.5 semantic memory dengan v3.6 Knowledge Graph:
#   QUERY → semantic search (v3.5) → candidate memories → extract entities
#   → graph expansion (terbatas) → relationship filtering → context ranking
#
# Prinsip:
#   - Memori tetap ADVISORY. Graph tidak menggantikan verified memory.
#   - Traversal SELALU dibatasi (max_depth/max_nodes/timeout implisit).
#   - Ranking punya reasons[] traceable (tidak ada skor ajaib).
#   - Scope project dihormati; node project lain tidak masuk konteks.
import time

from core import graph as G
from core import memory as M


def _weights():
    return {"semantic": 0.40, "entity": 0.20, "relation": 0.20, "scope": 0.10,
            "confidence": 0.05, "success": 0.05}


def query_entities(query, limit=8):
    """Entity yang benar-benar disebut query (bukan tebakan): search graph + lexical."""
    out, seen = [], set()
    for n in G.search(query, limit=limit):
        if n["id"] not in seen:
            seen.add(n["id"])
            out.append(n)
    return out


def expand(seed_nodes, max_depth=2, max_nodes=20, allowed_relations=None,
           confidence_threshold=0.0, project_scope=None):
    """Graph expansion terbatas dari seed entity. Return node + jalur relasi."""
    obs = {"traversals": 0, "depth": 0}
    nodes, paths = {}, []
    for s in seed_nodes:
        if len(nodes) >= max_nodes:
            break
        sg = G.subgraph(s["id"], max_depth=max_depth, max_nodes=max_nodes,
                        allowed_relations=allowed_relations,
                        confidence_threshold=confidence_threshold,
                        project_scope=project_scope)
        obs["traversals"] += 1
        obs["depth"] = max(obs["depth"], sg["depth_reached"])
        for n in sg["nodes"]:
            if n["id"] == s["id"]:
                continue
            if len(nodes) >= max_nodes:
                break
            nodes.setdefault(n["id"], n)
            paths.append({"from": s["name"], "node": n["name"], "type": n["type"],
                          "confidence": n.get("confidence")})
    return list(nodes.values()), paths, obs


def entity_match_score(memory, entity_nodes):
    """Berapa banyak entity query yang benar-benar disebut memori (bukti teks)."""
    if not entity_nodes:
        return 0.0
    hay = " ".join([memory.get("title", ""), memory.get("content", ""),
                    " ".join(memory.get("entities") or []),
                    " ".join(memory.get("tags") or [])]).lower()
    hits = 0
    for en in entity_nodes:
        nn = G.norm_name(en["name"])
        aliases = [G.norm_name(a) for a in (en.get("properties", {}).get("aliases") or [])]
        if any(tok and tok in hay for tok in [nn] + aliases):
            hits += 1
    return min(1.0, hits / max(1, len(entity_nodes)))


def relation_score(memory, expanded_nodes, paths, decay=0.5):
    """Kedekatan relasi: 1 hop = 1.0, hop berikutnya turun eksponensial."""
    if not expanded_nodes:
        return 0.0, []
    mem_ents = {G.norm_name(e) for e in (memory.get("entities") or [])}
    mem_text = (memory.get("title", "") + " " + memory.get("content", "")).lower()
    best, hits = 0.0, []
    for i, p in enumerate(paths):
        if p["node"].lower() in mem_text or G.norm_name(p["node"]) in mem_ents:
            score = decay ** min(i // 3, 3)
            if score > best:
                best = score
            hits.append(p["from"] + "→" + p["node"])
    return best, hits[:5]


def rank_candidates(memories, query, entity_nodes=None, project_id=None,
                    expanded=None, paths=None, top_k=5):
    """Relationship-aware ranking (Phase 14). Reasons selalu bisa ditelusuri."""
    w = _weights()
    entity_nodes = entity_nodes or []
    expanded = expanded or []
    paths = paths or []
    ranked = []
    for m in memories:
        try:
            base = M.rank_memory(m, M._norm(query) if hasattr(M, "_norm") else query,
                                 None, {"project_id": project_id})
            base_rel = float(base.get("relevance", 0.0)) if isinstance(base, dict) else 0.0
            base_reasons = list(base.get("reasons", [])) if isinstance(base, dict) else []
        except Exception:
            base_rel, base_reasons = 0.0, []
        em = entity_match_score(m, entity_nodes)
        rs, rhits = relation_score(m, expanded, paths)
        same_proj = 1.0 if (project_id and (m.get("project_id") or None) == project_id) else (
            0.5 if m.get("scope") == "GLOBAL" else 0.0)
        conf = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}.get(m.get("confidence"), 0.3)
        succ = float(m.get("success_count", 0)) / max(1, float(m.get("success_count", 0)
                                                             + m.get("failure_count", 0)))
        total = (w["semantic"] * base_rel + w["entity"] * em + w["relation"] * rs
                 + w["scope"] * same_proj + w["confidence"] * conf + w["success"] * succ)
        reasons = base_reasons + [
            f"entity_match={em:.2f}", f"relation={rs:.2f}",
            f"scope={same_proj:.2f}", f"confidence={conf:.2f}",
        ]
        if rhits:
            reasons.append("graph_paths=" + ",".join(rhits))
        ranked.append({"memory": m, "memory_id": m.get("id"), "score": round(total, 4),
                       "relevance": round(total, 4), "reasons": reasons,
                       "entity_match": round(em, 3), "relation_score": round(rs, 3),
                       "graph_hits": rhits})
    ranked.sort(key=lambda r: -r["score"])
    return ranked[:top_k] if top_k else ranked


def linked_context(query, project_id=None, top_k=5, max_depth=2, max_nodes=20,
                   allowed_relations=None, confidence_threshold=0.0):
    """Pipeline Phase 12: semantic → entities → graph expansion → ranking."""
    t0 = time.time()
    G.obs_inc("graph_queries")
    scored = M.hybrid_search(query, top_k=max(top_k * 3, 10),
                             ctx={"project_id": project_id}, max_items=None)
    memories = [s["memory"] for s in (scored or []) if isinstance(s, dict) and s.get("memory")]
    seeds = query_entities(query, limit=8)
    expanded, paths, obs = ([], [], {"traversals": 0, "depth": 0})
    if seeds:
        expanded, paths, obs = expand(seeds, max_depth=max_depth, max_nodes=max_nodes,
                                      allowed_relations=allowed_relations,
                                      confidence_threshold=confidence_threshold,
                                      project_scope=project_id)
    ranked = rank_candidates(memories, query, seeds, project_id, expanded, paths, top_k=top_k)
    return {"query": query, "memories": [r["memory"] for r in ranked],
            "scores": ranked, "seed_entities": [s["name"] for s in seeds],
            "graph_nodes": [n["name"] for n in expanded],
            "graph_paths": paths[:20], "graph_observability": obs,
            "latency_ms": int((time.time() - t0) * 1000)}


def context_block(query, project_id=None, top_k=5, max_chars=2500):
    """Blok konteks siap-inject ke planner (ringkas, traceable)."""
    res = linked_context(query, project_id=project_id, top_k=top_k)
    lines = []
    if res["seed_entities"]:
        lines.append("ENTITY DIKENAL: " + ", ".join(res["seed_entities"][:8]))
    if res["graph_paths"]:
        lines.append("RELASI GRAPH (bukti eksplisit, 1-2 hop):")
        for p in res["graph_paths"][:8]:
            lines.append(f"- {p['from']} → {p['node']} [{p['type']}]")
    if res["memories"]:
        lines.append("MEMORI TER-RANK (advisory — verifikasi sebelum dipakai):")
        for r in res["scores"]:
            m = r["memory"]
            lines.append(f"- [{r['score']:.2f}|{m.get('type')}|{m.get('quality')}] "
                         f"{(m.get('title') or '')[:80]} :: {(m.get('content') or '')[:120]} "
                         f"(reasons: {', '.join(r['reasons'][:4])})")
    text = "\n".join(lines)
    return text[:max_chars], res


if __name__ == "__main__":
    print(context_block("fix api timeout"))