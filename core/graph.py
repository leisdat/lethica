# core/graph.py — v3.6.0 Knowledge Graph (structured relationship layer)
#
# Tambahan di atas v3.5 semantic memory. TIDAK mengganti memory.
# Storage = JSON lokal (graph/nodes.json, graph/edges.json, graph/index.json) — offline, no Neo4j.
# Semua modul lain WAJIB lewat API di file ini; JANGAN sentuh storage mentah.
#
# Prinsip (dari mission v3.6):
#   - Relations harus eksplisit + ada evidence. DILARANG infer relasi berbahaya tanpa bukti.
#   - DILARANG menganggap korelasi sebagai kausalitas.
#   - DILARANG merge entity ambigu otomatis.
#   - DILARANG overwrite historical state.
#   - DILARANG bocorkan knowledge project-scoped ke project lain.
#   - DILARANG traversal tanpa batas.
#   - DILARANG simpan secret.
#
# API (Phase 5):
#   add_node get_node update_node remove_node
#   add_edge get_edges neighbors find_path subgraph
#   search find_related detect_cycles validate
import os
import re
import json
import time
import threading
from collections import defaultdict, deque
from datetime import datetime, timezone

from core import config

GRAPH_DIR = os.environ.get("LETHICA_GRAPH_DIR") or os.path.join(config.LETHICA_DIR, "graph")
NODES_FILE = os.path.join(GRAPH_DIR, "nodes.json")
EDGES_FILE = os.path.join(GRAPH_DIR, "edges.json")
INDEX_FILE = os.path.join(GRAPH_DIR, "index.json")
GOBS_FILE = os.path.join(GRAPH_DIR, "observability.json")
os.makedirs(GRAPH_DIR, exist_ok=True)

MAX_NODES = 5000
MAX_EDGES = 20000
MAX_HISTORY = 20          # state history per node (Phase 10)

# ── Phase 2: node types ──────────────────────────────────────────────
NODE_TYPES = {
    "PROJECT", "TASK", "GOAL", "AGENT", "SKILL", "SKILL_VERSION", "STRATEGY",
    "STRATEGY_VERSION", "TOOL", "FILE", "DIRECTORY", "SERVICE", "API", "PACKAGE",
    "DEPENDENCY", "ERROR", "FAILURE", "SOLUTION", "LESSON", "DECISION", "FACT",
    "MEMORY", "EXECUTION", "ENVIRONMENT", "CONFIGURATION", "COMPONENT", "SOURCE",
}

# ── Phase 3: relation types ──────────────────────────────────────────
RELATION_TYPES = {
    "USES", "DEPENDS_ON", "CONTAINS", "PART_OF", "CREATED_BY", "EXECUTED_BY",
    "REQUIRES", "PRODUCES", "MODIFIES", "READS", "WRITES", "CALLS", "FAILS_WITH",
    "FAILED_WITH", "CAUSED_BY", "FIXED_BY", "SOLVED_BY", "VALIDATED_BY",
    "IMPROVES", "REPLACED_BY", "SUPERSEDES", "RELATED_TO", "SIMILAR_TO",
    "DERIVED_FROM", "USED_IN", "USED_BY", "WORKS_WITH", "CONFLICTS_WITH",
    "SUPPORTED_BY", "DEPLOYED_TO", "CONFIGURED_BY", "UPGRADED_TO", "HAS_VERSION",
    "DETECTED_BY", "REPAIRED_BY", "OCCURRED_IN", "SUCCEEDED_IN", "SUPPORTS",
    "VERSION", "REQUIRED_BY", "KNOWN_BY",
}

# Relasi simetris → arah bebas.
SYMMETRIC_RELATIONS = {"RELATED_TO", "SIMILAR_TO", "CONFLICTS_WITH", "WORKS_WITH"}

# Relasi kausal → traversal BALIK dilarang (hindari inverse-causation fallacy).
CAUSAL_RELATIONS = {
    "CAUSED_BY", "FIXED_BY", "SOLVED_BY", "VALIDATED_BY", "PRODUCES",
    "FAILS_WITH", "FAILED_WITH", "DETECTED_BY", "REPAIRED_BY", "IMPROVES",
    "HAS_VERSION", "UPGRADED_TO", "SUPERSEDES", "REPLACED_BY", "SUPPORTS",
}
REVERSE_FACTOR = 0.4      # bobot relasi saat ditelusuri balik (Phase 14)

CONF_SCORES = {"LOW": 0.3, "MEDIUM": 0.6, "HIGH": 0.9}
SCOPES = {"GLOBAL", "PROJECT", "TASK", "SKILL", "STRATEGY"}
NODE_STATUS = {"ACTIVE", "STALE", "CONFLICTED", "UNKNOWN", "ARCHIVED", "HISTORICAL", "CURRENT"}
FRESHNESS = {"CURRENT", "STALE", "UNKNOWN", "CONFLICTED"}
SOURCES = {"LETHICA_INFERENCE", "WEB_EVIDENCE", "EXECUTION_EVIDENCE", "USER_INPUT", "GRAPH_INFERENCE"}

_LOCK = threading.RLock()

# reuse v3.5 secret detection — satu sumber kebenaran
from core.memory import redact as _redact  # noqa: E402


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").timestamp()
    except Exception:
        return 0.0


def norm_name(name):
    """Normalisasi nama entity utk index/alias (Phase 7). Bukan merge otomatis."""
    n = (name or "").strip().lower()
    n = re.sub(r"[\s_\-]+", " ", n)
    return re.sub(r"[^a-z0-9 .:/@+]", "", n).strip()


def _nid(text):
    return hashlib_md5(norm_name(text) + "|" + str(time.time()))


def hashlib_md5(text):
    import hashlib
    if isinstance(text, bytes):
        return hashlib.md5(text).hexdigest()
    return hashlib.md5(str(text).encode("utf-8")).hexdigest()


# ── storage ──────────────────────────────────────────────────────────
def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _nodes():
    return _load(NODES_FILE, [])


def _edges():
    return _load(EDGES_FILE, [])


def _save_nodes(lst):
    _save(NODES_FILE, lst[-MAX_NODES:])


def _save_edges(lst):
    _save(EDGES_FILE, lst[-MAX_EDGES:])


# ── Phase 36: observability ──────────────────────────────────────────
GOBS_DEFAULT = {
    "nodes_created": 0, "nodes_updated": 0, "nodes_removed": 0,
    "edges_created": 0, "edges_updated": 0, "edges_removed": 0,
    "entities_resolved": 0, "entities_unresolved": 0,
    "graph_queries": 0, "graph_traversals": 0, "traversal_depth_total": 0,
    "graph_latency_ms": 0, "world_model_updates": 0,
    "conflicts": 0, "stale_nodes": 0, "stale_edges": 0,
    "impact_analysis_count": 0, "validation_runs": 0,
    "world_queries": 0, "llm_extractions": 0, "temporal_updates": 0,
}


def _load_gobs():
    d = _load(GOBS_FILE, {})
    out = dict(GOBS_DEFAULT)
    if isinstance(d, dict):
        out.update({k: v for k, v in d.items() if k in GOBS_DEFAULT})
    return out


def obs_inc(*keys, amount=1):
    with _LOCK:
        d = _load_gobs()
        for k in keys:
            if k in d:
                d[k] += amount
        _save(GOBS_FILE, d)


def obs_set(key, value):
    with _LOCK:
        d = _load_gobs()
        if key in d:
            d[key] = value
        _save(GOBS_FILE, d)


def observability():
    return _load_gobs()


# ── index (Phase 4) ──────────────────────────────────────────────────
def _build_index(nodes):
    by_name = {}
    aliases = {}
    by_type = defaultdict(list)
    for n in nodes:
        key = (norm_name(n.get("name", "")), n.get("type", ""))
        by_name.setdefault(key, n["id"])
        for al in n.get("properties", {}).get("aliases", []) or []:
            aliases.setdefault((norm_name(al), n.get("type", "")), n["id"])
        by_type[n.get("type", "")].append(n["id"])
    return {"by_name": {f"{k[0]}|{k[1]}": v for k, v in by_name.items()},
            "aliases": {f"{k[0]}|{k[1]}": v for k, v in aliases.items()},
            "by_type": dict(by_type)}


def _index():
    idx = _load(INDEX_FILE, None)
    if not isinstance(idx, dict) or "by_name" not in idx:
        idx = _build_index(_nodes())
        _save(INDEX_FILE, idx)
    return idx


def rebuild_index():
    with _LOCK:
        idx = _build_index(_nodes())
        _save(INDEX_FILE, idx)
    return idx


def _index_put(node):
    idx = _index()
    idx["by_name"][f"{norm_name(node['name'])}|{node['type']}"] = node["id"]
    for al in node.get("properties", {}).get("aliases", []) or []:
        idx["aliases"][f"{norm_name(al)}|{node['type']}"] = node["id"]
    idx["by_type"].setdefault(node["type"], [])
    if node["id"] not in idx["by_type"][node["type"]]:
        idx["by_type"][node["type"]].append(node["id"])
    _save(INDEX_FILE, idx)


def _index_drop(node):
    idx = _index()
    idx["by_name"].pop(f"{norm_name(node['name'])}|{node['type']}", None)
    for al in node.get("properties", {}).get("aliases", []) or []:
        idx["aliases"].pop(f"{norm_name(al)}|{node['type']}", None)
    if node["type"] in idx["by_type"]:
        idx["by_type"][node["type"]] = [i for i in idx["by_type"][node["type"]] if i != node["id"]]
    _save(INDEX_FILE, idx)


def find_by_name(name, type=None):
    """Lookup node via index (exact normalized) → alias. Return node dict atau None."""
    idx = _index()
    n = norm_name(name)
    if type:
        hit = idx["by_name"].get(f"{n}|{type}") or idx["aliases"].get(f"{n}|{type}")
        return get_node(hit) if hit else None
    for key, nid in list(idx["by_name"].items()) + list(idx["aliases"].items()):
        if key.rsplit("|", 1)[0] == n:
            return get_node(nid)
    return None


# ── Phase 1: node model ──────────────────────────────────────────────
def make_node(type, name, description="", properties=None, source="LETHICA_INFERENCE",
              confidence=None, project_id=None, scope=None, status="ACTIVE",
              valid_from=None, valid_until=None, version=None, node_id=None):
    if type not in NODE_TYPES:
        raise ValueError(f"invalid node type: {type}")
    if source not in SOURCES:
        raise ValueError(f"invalid source: {source}")
    props = dict(properties or {})
    scope = scope or ("PROJECT" if project_id else "GLOBAL")
    if scope not in SCOPES:
        raise ValueError(f"invalid scope: {scope}")
    conf = confidence
    if conf not in CONF_SCORES:
        conf = {"EXECUTION_EVIDENCE": "MEDIUM", "USER_INPUT": "MEDIUM",
                "WEB_EVIDENCE": "LOW", "GRAPH_INFERENCE": "LOW"}.get(source, "LOW")
    now = _now()
    return {
        "id": node_id or ("n" + hashlib_md5(norm_name(f"{type}:{name}:{project_id or ''}")
                                            + str(int(time.time() * 1000)))[:16]),
        "type": type,
        "name": _redact(str(name)[:200]),
        "description": _redact(str(description or "")[:1000]),
        "properties": _clean_props(props),
        "source": source,
        "confidence": conf,
        "confidence_score": CONF_SCORES[conf],
        "project_id": project_id,
        "scope": scope,
        "status": status,
        "created_at": now,
        "updated_at": now,
        "version": version,
        "valid_from": valid_from or now,
        "valid_until": valid_until,
        "freshness": "CURRENT",
        "last_verified": now,
        "history": [],
    }


def _clean_props(props):
    out = {}
    for k, v in (props or {}).items():
        if isinstance(v, str):
            out[k] = _redact(v[:500])
        elif isinstance(v, (list, tuple)):
            out[k] = [_redact(x[:200]) if isinstance(x, str) else x for x in v[:30]]
        elif isinstance(v, dict):
            out[k] = _clean_props(v)
        else:
            out[k] = v
    return out


def _find_dup_node(node, nodes):
    """Dup = sama type + sama normalized name + sama project scope."""
    for ex in nodes:
        if (ex["type"] == node["type"]
                and norm_name(ex["name"]) == norm_name(node["name"])
                and (ex.get("project_id") or None) == (node.get("project_id") or None)):
            return ex
    return None


def add_node(type, name, description="", properties=None, source="LETHICA_INFERENCE",
             confidence=None, project_id=None, scope=None, status="ACTIVE",
             version=None, dedupe=True, node_id=None):
    """Tambah node. Dedupe by (type, normalized name, project). Return dict hasil."""
    with _LOCK:
        node = make_node(type, name, description, properties, source, confidence,
                         project_id, scope, status, version=version, node_id=node_id)
        nodes = _nodes()
        if dedupe:
            dup = _find_dup_node(node, nodes)
            if dup:
                obs_inc("nodes_updated")
                upd = update_node(dup["id"], {"description": node["description"],
                                              "properties": _merge_props(dup, node),
                                              "confidence": _max_conf(dup, node),
                                              "updated_at": _now()}, merge_history=False)
                return {"ok": True, "action": "MERGED", "node": upd}
        nodes.append(node)
        _save_nodes(nodes)
        _index_put(node)
    obs_inc("nodes_created")
    return {"ok": True, "action": "CREATED", "node": node}


def _merge_props(old, new):
    p = dict(old.get("properties") or {})
    for k, v in (new.get("properties") or {}).items():
        if k == "aliases":
            merged = list(dict.fromkeys((p.get("aliases") or []) + (v or [])))
            p[k] = merged[:20]
        elif k not in p or p[k] in (None, "", [], {}):
            p[k] = v
    return p


def _max_conf(a, b):
    order = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    return a["confidence"] if order.get(a.get("confidence"), 0) >= order.get(b.get("confidence"), 0) else b["confidence"]


def get_node(node_id):
    for n in _nodes():
        if n["id"] == node_id:
            return n
    return None


def update_node(node_id, patch, merge_history=True, record_state=True):
    """Patch node. Stateless history: nilai lama non-null disimpan (Phase 10)."""
    with _LOCK:
        nodes = _nodes()
        for i, n in enumerate(nodes):
            if n["id"] != node_id:
                continue
            patch = dict(patch or {})
            old = dict(n)
            if record_state:
                hist = n.setdefault("history", [])
                snapshot = {k: old.get(k) for k in ("version", "status", "freshness",
                                                    "properties", "confidence", "valid_until")
                            if old.get(k) not in (None, "", {}, [])}
                if snapshot:
                    hist.append({"at": old.get("updated_at"), "state": snapshot})
                    n["history"] = hist[-MAX_HISTORY:]
            for k, v in patch.items():
                if k == "properties":
                    n["properties"] = _merge_props(n, {"properties": v}) if merge_history else _clean_props(v)
                elif k == "history":
                    continue
                else:
                    n[k] = _redact(v[:1000]) if isinstance(v, str) else v
            if "confidence" in patch and patch["confidence"] in CONF_SCORES:
                n["confidence_score"] = CONF_SCORES[patch["confidence"]]
            if patch.get("status") == "CURRENT":
                n["freshness"] = "CURRENT"
                n["last_verified"] = _now()
            n["updated_at"] = _now()
            nodes[i] = n
            _save_nodes(nodes)
            _index_put(n)
            obs_inc("nodes_updated")
            return n
    return None


def remove_node(node_id, cascade=True):
    """Hapus node (+ edge terkait kalau cascade). Return dict hasil."""
    with _LOCK:
        nodes = _nodes()
        target = next((n for n in nodes if n["id"] == node_id), None)
        if not target:
            return {"ok": False, "reason": "node not found"}
        nodes = [n for n in nodes if n["id"] != node_id]
        _save_nodes(nodes)
        _index_drop(target)
        removed_edges = 0
        if cascade:
            edges = _edges()
            keep = [e for e in edges if e["source_node"] != node_id and e["target_node"] != node_id]
            removed_edges = len(edges) - len(keep)
            _save_edges(keep)
    obs_inc("nodes_removed")
    if removed_edges:
        obs_inc("edges_removed", amount=removed_edges)
    return {"ok": True, "node": node_id, "edges_removed": removed_edges}


# ── Phase 1: edge model ─────────────────────────────────────────────
def make_edge(source_node, relation, target_node, properties=None,
              source="LETHICA_INFERENCE", confidence=None, valid_from=None,
              valid_until=None, status="ACTIVE"):
    if relation not in RELATION_TYPES:
        raise ValueError(f"invalid relation: {relation}")
    if source not in SOURCES:
        raise ValueError(f"invalid source: {source}")
    conf = confidence if confidence in CONF_SCORES else (
        {"EXECUTION_EVIDENCE": "MEDIUM", "USER_INPUT": "MEDIUM",
         "WEB_EVIDENCE": "LOW", "GRAPH_INFERENCE": "LOW"}.get(source, "LOW"))
    now = _now()
    return {
        "id": "e" + hashlib_md5(f"{source_node}|{relation}|{target_node}|{time.time()}"
                                .encode())[:16],
        "source_node": source_node,
        "relation": relation,
        "target_node": target_node,
        "properties": _clean_props(properties or {}),
        "source": source,
        "confidence": conf,
        "confidence_score": CONF_SCORES[conf],
        "created_at": now,
        "updated_at": now,
        "valid_from": valid_from or now,
        "valid_until": valid_until,
        "status": status,
    }


def add_edge(source_node, relation, target_node, properties=None,
             source="LETHICA_INFERENCE", confidence=None, strict=True,
             valid_from=None, valid_until=None):
    """Tambah edge. strict=False → boleh dangling/self (utk validasi & failure test)."""
    if relation not in RELATION_TYPES:
        return {"ok": False, "reason": f"invalid relation: {relation}"}
    with _LOCK:
        nodes = {n["id"]: n for n in _nodes()}
        problems = []
        if source_node not in nodes:
            problems.append("missing source node")
        if target_node not in nodes:
            problems.append("missing target node")
        if source_node == target_node:
            problems.append("self relation")
        if problems and strict:
            return {"ok": False, "reason": "; ".join(problems), "problems": problems}
        edges = _edges()
        for ex in edges:
            if (ex["source_node"] == source_node and ex["relation"] == relation
                    and ex["target_node"] == target_node):
                ex["properties"] = _merge_props(ex, {"properties": properties or {}})
                if confidence in CONF_SCORES:
                    ex["confidence"] = confidence
                    ex["confidence_score"] = CONF_SCORES[confidence]
                ex["updated_at"] = _now()
                _save_edges(edges)
                obs_inc("edges_updated")
                return {"ok": True, "action": "UPDATED", "edge": ex,
                        "problems": problems}
        edge = make_edge(source_node, relation, target_node, properties, source,
                         confidence, valid_from, valid_until)
        edges.append(edge)
        _save_edges(edges)
    obs_inc("edges_created")
    return {"ok": True, "action": "CREATED", "edge": edge, "problems": problems}


def get_edges(node_id=None, relation=None, direction="both", include_expired=False,
              project_scope=None):
    """Ambil edge. direction: out|in|both. Return list edge (+ field _direction)."""
    out = []
    for e in _edges():
        if relation and e["relation"] != relation:
            continue
        if not include_expired and e.get("valid_until") and _ts(e["valid_until"]) < time.time():
            continue
        if node_id:
            if e["source_node"] == node_id:
                e = dict(e, _direction="out")
            elif e["target_node"] == node_id:
                e = dict(e, _direction="in")
            else:
                continue
            if direction == "out" and e["_direction"] != "out":
                continue
            if direction == "in" and e["_direction"] != "in":
                continue
        out.append(e)
    return out


def edges_between(a, b):
    return [e for e in _edges()
            if {e["source_node"], e["target_node"]} == {a, b}]


def neighbors(node_id, direction="both", allowed_relations=None,
              confidence_threshold=0.0, project_scope=None, include_expired=False):
    """Tetangga langsung. Relasi kausal tidak ditelusuri balik (Phase 15).

    Return list of dict: {node, node_id, via, relation, direction, weight, confidence}
    """
    nodes = {n["id"]: n for n in _nodes()}
    out = []
    for e in _edges():
        if e["source_node"] != node_id and e["target_node"] != node_id:
            continue
        if not include_expired and e.get("valid_until") and _ts(e["valid_until"]) < time.time():
            continue
        rel = e["relation"]
        if allowed_relations and rel not in allowed_relations:
            continue
        if e.get("confidence_score", 0.3) < confidence_threshold:
            continue
        direction_flag = "out" if e["source_node"] == node_id else "in"
        if direction == "out" and direction_flag != "out":
            continue
        if direction == "in" and direction_flag != "in":
            continue
        reverse = direction_flag == "in" and rel not in SYMMETRIC_RELATIONS
        if reverse and rel in CAUSAL_RELATIONS:
            continue  # inverse-causation tidak diizinkan
        other_id = e["target_node"] if direction_flag == "out" else e["source_node"]
        other = nodes.get(other_id)
        if not other:
            continue
        if project_scope and other.get("project_id") and other["project_id"] != project_scope \
                and other.get("scope") == "PROJECT":
            continue
        out.append({"node": other, "node_id": other_id, "via": rel,
                    "relation": rel, "direction": direction_flag,
                    "weight": 1.0 if not reverse else REVERSE_FACTOR,
                    "evidence": e.get("properties", {}).get("evidence"),
                    "confidence": e.get("confidence"),
                    "confidence_score": e.get("confidence_score", 0.3),
                    "edge_id": e["id"]})
    return out


def find_path(a, b, max_depth=3, allowed_relations=None, direction="out"):
    """BFS terbatas. Return list path [{node, relation}] atau [] kalau gak ada."""
    obs_inc("graph_queries")
    start = time.time()
    if a == b:
        node = get_node(a)
        return [{"node": node, "relation": None}] if node else []
    frontier = deque([(a, [{"node": get_node(a), "relation": None}])])
    seen = {a}
    depth = 0
    while frontier and depth < max_depth:
        depth += 1
        for _ in range(len(frontier)):
            cur, path = frontier.popleft()
            for nb in neighbors(cur, direction=direction,
                                allowed_relations=allowed_relations):
                nid = nb["node_id"]
                if nid in seen:
                    continue
                newpath = path + [{"node": nb["node"], "relation": nb["relation"]}]
                if nid == b:
                    obs_set("graph_latency_ms", int((time.time() - start) * 1000))
                    return newpath
                seen.add(nid)
                frontier.append((nid, newpath))
    obs_set("graph_latency_ms", int((time.time() - start) * 1000))
    return []


def subgraph(root_id, max_depth=2, max_nodes=25, allowed_relations=None,
             confidence_threshold=0.0, project_scope=None):
    """Traversal terbatas (Phase 13/35). Return {root, nodes, edges, depth_reached}."""
    obs_inc("graph_queries", "graph_traversals")
    start = time.time()
    root = get_node(root_id)
    if not root:
        return {"root": None, "nodes": [], "edges": [], "depth_reached": 0}
    nodes = {root_id: root}
    edge_ids = {}
    frontier = [root_id]
    depth = 0
    while frontier and depth < max_depth and len(nodes) < max_nodes:
        depth += 1
        nxt = []
        for cur in frontier:
            for nb in neighbors(cur, allowed_relations=allowed_relations,
                                confidence_threshold=confidence_threshold,
                                project_scope=project_scope):
                edge_ids[nb["edge_id"]] = True
                if nb["node_id"] in nodes:
                    continue
                if len(nodes) >= max_nodes:
                    break
                nodes[nb["node_id"]] = nb["node"]
                nxt.append(nb["node_id"])
        frontier = nxt
    obs_inc("traversal_depth_total", amount=depth)
    obs_set("graph_latency_ms", int((time.time() - start) * 1000))
    edges = [e for e in _edges() if e["id"] in edge_ids]
    return {"root": root, "nodes": list(nodes.values()), "edges": edges,
            "depth_reached": depth, "truncated": len(nodes) >= max_nodes}


def search(query, type=None, limit=10):
    """Cari node by name/description (lexical). Return list node."""
    obs_inc("graph_queries")
    from core.experience import _norm
    q = _norm(query)
    if not q:
        return []
    qw = set(q.split())
    scored = []
    for n in _nodes():
        if type and n["type"] != type:
            continue
        text = _norm(f"{n['name']} {n.get('description','')} "
                     f"{' '.join(n.get('properties',{}).get('aliases',[]) or [])}")
        w = set(text.split())
        nn = norm_name(n["name"])
        sub = (nn and (nn in q or q in nn))
        overlap = len(qw & w)
        if not overlap and not sub:
            continue
        score = overlap / max(1, len(qw))
        if sub:
            score += 0.5
        scored.append((score, n))
    scored.sort(key=lambda t: -t[0])
    return [n for _, n in scored[:limit]]


def find_related(node_id, limit=10, max_depth=2):
    """Node terkait via traversal terbatas + bobot jalur."""
    sg = subgraph(node_id, max_depth=max_depth, max_nodes=limit + 1)
    out = [n for n in sg["nodes"] if n["id"] != node_id]
    out.sort(key=lambda n: n.get("confidence_score", 0), reverse=True)
    return out[:limit]


def detect_cycles(max_depth=6, limit=20):
    """Deteksi cycle sederhana (DFS iteratif). Return list of node-id list."""
    nodes = _nodes()
    adj = defaultdict(list)
    for e in _edges():
        if e["relation"] in SYMMETRIC_RELATIONS:
            continue  # simetris bukan cycle bermakna
        adj[e["source_node"]].append(e["target_node"])
    cycles = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n["id"]: WHITE for n in nodes}
    for n in nodes:
        if color[n["id"]] != WHITE:
            continue
        stack = [(n["id"], iter(adj.get(n["id"], [])))]
        color[n["id"]] = GRAY
        path = [n["id"]]
        while stack:
            cur, it = stack[-1]
            advanced = False
            for nxt in it:
                if len(path) > max_depth:
                    break
                if color.get(nxt, WHITE) == GRAY:
                    idx = path.index(nxt) if nxt in path else 0
                    cyc = path[idx:] + [nxt]
                    if cyc not in cycles:
                        cycles.append(cyc)
                    if len(cycles) >= limit:
                        return cycles
                elif color.get(nxt, WHITE) == WHITE:
                    color[nxt] = GRAY
                    path.append(nxt)
                    stack.append((nxt, iter(adj.get(nxt, []))))
                    advanced = True
                break
            if not advanced:
                color[stack[-1][0]] = BLACK
                stack.pop()
                if path:
                    path.pop()
    return cycles


def validate(auto_fix=False):
    """Phase 23: deteksi dangling edge, missing node, invalid relation, duplicate,
    self-relation, malformed ref, corrupted record. TIDAK auto-fix konflik semantik."""
    obs_inc("validation_runs")
    nodes = _nodes()
    edges = _edges()
    ids = {n["id"] for n in nodes}
    issues = {"dangling_edges": [], "missing_nodes": [], "invalid_relations": [],
              "duplicate_relations": [], "self_relations": [], "malformed_nodes": [],
              "malformed_edges": [], "cycles": []}
    for n in nodes:
        if not n.get("id") or n.get("type") not in NODE_TYPES or not n.get("name"):
            issues["malformed_nodes"].append(n.get("id"))
    seen = set()
    for e in edges:
        if not e.get("id") or e.get("relation") not in RELATION_TYPES:
            issues["invalid_relations"].append(e.get("id"))
            continue
        if e["source_node"] not in ids:
            issues["dangling_edges"].append(e["id"])
            issues["missing_nodes"].append(e["source_node"])
        if e["target_node"] not in ids:
            issues["dangling_edges"].append(e["id"])
            issues["missing_nodes"].append(e["target_node"])
        if e["source_node"] == e["target_node"]:
            issues["self_relations"].append(e["id"])
        key = (e["source_node"], e["relation"], e["target_node"], e.get("valid_from"))
        if key in seen:
            issues["duplicate_relations"].append(e["id"])
        seen.add(key)
    issues["cycles"] = detect_cycles()
    issues["ok"] = not any(v for k, v in issues.items() if k != "ok")
    issues["counts"] = {k: len(v) for k, v in issues.items() if isinstance(v, list)}
    return issues


# ── Phase 10/11: temporal state ──────────────────────────────────────
def update_state(node_id, version=None, properties=None, status="CURRENT",
                 confidence=None, source="EXECUTION_EVIDENCE", reason=""):
    """Update state node + simpan state lama sebagai HISTORICAL (TIDAK overwrite).
    Return {ok, node, previous, transition}. Historical disimpan sebagai state di history
    PLUS node ... SUCCEEDED/UPGRADED_TO relation saat ada version transition.
    """
    with _LOCK:
        node = get_node(node_id)
        if not node:
            return {"ok": False, "reason": "node not found"}
        prev_version = node.get("version")
        prev_state = {"version": prev_version, "status": node.get("status"),
                      "freshness": node.get("freshness"),
                      "properties": dict(node.get("properties") or {})}
        patch = {"status": status, "freshness": "CURRENT", "last_verified": _now()}
        if version:
            patch["version"] = version
        if confidence in CONF_SCORES:
            patch["confidence"] = confidence
        if properties:
            patch["properties"] = properties
        upd = update_node(node_id, patch, record_state=True)
        obs_inc("temporal_updates")
        transition = None
        if version and prev_version and version != prev_version:
            prev_node = find_by_name(f"{node['name']} {prev_version}", type=node["type"]) \
                if False else None
            transition = {"from_version": prev_version, "to_version": version,
                          "at": _now(), "reason": reason}
            upd.setdefault("history", [])
            # catat transisi eksplisit supaya historical state tetap bisa ditelusuri
            hist = get_node(node_id).get("history", [])
            if hist:
                hist[-1]["transition"] = transition
                nodes = _nodes()
                for i, n in enumerate(nodes):
                    if n["id"] == node_id:
                        nodes[i]["history"] = hist
                _save_nodes(nodes)
        return {"ok": True, "node": upd, "previous": prev_state, "transition": transition}


def state_history(node_id):
    """Riwayat state (current dulu, lalu historical). Historical TIDAK dihapus."""
    n = get_node(node_id)
    if not n:
        return []
    out = [{"at": n.get("updated_at"), "state": {"version": n.get("version"),
                                                 "status": n.get("status"),
                                                 "freshness": n.get("freshness"),
                                                 "properties": n.get("properties")},
            "current": True}]
    for h in reversed(n.get("history", []) or []):
        out.append({"at": h.get("at"), "state": h.get("state"), "current": False,
                    "transition": h.get("transition")})
    return out


def set_validity(edge_id, valid_from=None, valid_until=None):
    with _LOCK:
        edges = _edges()
        for e in edges:
            if e["id"] == edge_id:
                if valid_from:
                    e["valid_from"] = valid_from
                if valid_until:
                    e["valid_until"] = valid_until
                e["updated_at"] = _now()
                _save_edges(edges)
                obs_inc("edges_updated")
                return e
    return None


def expire_edge(edge_id, when=None):
    return set_validity(edge_id, valid_until=when or _now())


# ── Phase 32: freshness ──────────────────────────────────────────────
def refresh_freshness(stale_days=30):
    """Classify CURRENT/STALE/UNKNOWN/CONFLICTED berdasar last_verified + status."""
    with _LOCK:
        nodes = _nodes()
        now = time.time()
        stale = 0
        for n in nodes:
            if n.get("status") == "CONFLICTED":
                n["freshness"] = "CONFLICTED"
            elif not n.get("last_verified"):
                n["freshness"] = "UNKNOWN"
            elif (now - _ts(n["last_verified"])) > stale_days * 86400:
                n["freshness"] = "STALE"
                stale += 1
            else:
                n["freshness"] = "CURRENT"
        _save_nodes(nodes)
        obs_set("stale_nodes", stale)
    return {"stale": stale, "total": len(nodes)}


def mark_conflict(node_id, reason="", other_id=None, evidence=None):
    """Tandai CONFLICTED + edge CONFLICTS_WITH (bukti eksplisit, bukan tebakan)."""
    upd = update_node(node_id, {"status": "CONFLICTED", "freshness": "CONFLICTED"})
    obs_inc("conflicts")
    if other_id:
        add_edge(node_id, "CONFLICTS_WITH", other_id,
                 properties={"reason": reason, "evidence": evidence or []},
                 source="EXECUTION_EVIDENCE")
    return {"ok": bool(upd), "node": upd, "reason": reason}


def mark_stale(edge_ids=None, node_ids=None):
    with _LOCK:
        if edge_ids:
            edges = _edges()
            for e in edges:
                if e["id"] in set(edge_ids):
                    e["status"] = "STALE"
            _save_edges(edges)
            obs_inc("stale_edges", amount=len(edge_ids))
        if node_ids:
            for nid in node_ids:
                update_node(nid, {"freshness": "STALE"})
                obs_inc("stale_nodes")
    return {"ok": True}


# ── Phase 34: scope isolation ────────────────────────────────────────
def scoped_nodes(project_id, include_global=True, types=None):
    """Node yang boleh dilihat dari sebuah project. GLOBAL boleh, PROJECT lain TIDAK."""
    out = []
    for n in _nodes():
        if types and n["type"] not in types:
            continue
        if n.get("scope") == "PROJECT":
            if n.get("project_id") != project_id:
                continue
        elif not include_global:
            continue
        out.append(n)
    return out


def visible(node_or_id, project_id):
    """Cek apakah node boleh dilihat dari project_id."""
    n = node_or_id if isinstance(node_or_id, dict) else get_node(node_or_id)
    if not n:
        return False
    if n.get("scope") != "PROJECT":
        return True
    return (n.get("project_id") or None) == (project_id or None)


# ── stats ────────────────────────────────────────────────────────────
def summary():
    nodes = _nodes()
    edges = _edges()
    by_type = defaultdict(int)
    for n in nodes:
        by_type[n["type"]] += 1
    by_rel = defaultdict(int)
    for e in edges:
        by_rel[e["relation"]] += 1
    return (f"Knowledge Graph v3.6: {len(nodes)} nodes / {len(edges)} edges. "
            f"types: " + " · ".join(f"{k}={v}" for k, v in sorted(by_type.items())[:8])
            + " | rel: " + " · ".join(f"{k}={v}" for k, v in sorted(by_rel.items())[:8]))


def reset(confirm=False):
    """Hapus seluruh graph (butuh confirm=True). Utk test isolation."""
    if not confirm:
        return {"ok": False, "reason": "confirm required"}
    with _LOCK:
        _save_nodes([])
        _save_edges([])
        _save(INDEX_FILE, {"by_name": {}, "aliases": {}, "by_type": {}})
    return {"ok": True}


if __name__ == "__main__":
    print(summary())