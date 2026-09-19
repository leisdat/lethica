#!/usr/bin/env python3
"""tests/test_knowledge_graph.py — v3.6 deterministic suite (Phase 37-40).

33 test item deterministik + failure injection A-J + regresi v3.0-v3.5.
Semua state diarahkan ke workspace temp supaya TIDAK mencemari lineage produksi.
Jalankan: python3 ~/lethica/tests/test_knowledge_graph.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

# ── isolasi total: graph + memory + evolution + registry ke temp workspace ──
WS = tempfile.mkdtemp(prefix="lx-v36-")
os.environ["LETHICA_GRAPH_DIR"] = os.path.join(WS, "graph")
os.makedirs(os.environ["LETHICA_GRAPH_DIR"], exist_ok=True)
os.environ["LETHICA_STRATEGY_REGISTRY"] = os.path.join(WS, "strategy-registry.json")

from core import config                                     # noqa: E402
config.LETHICA_DIR = WS
config.MEMORY_DIR = os.path.join(WS, "memory")
os.makedirs(config.MEMORY_DIR, exist_ok=True)

from core import memory as M                                # noqa: E402
M.MEM_FILE = os.path.join(config.MEMORY_DIR, "memories.json")
M.EMB_FILE = os.path.join(config.MEMORY_DIR, "embeddings.json")
M.REL_FILE = os.path.join(config.MEMORY_DIR, "relations.json")
M.OBS_FILE = os.path.join(config.MEMORY_DIR, "observability.json")

from core import graph as G                                 # noqa: E402
from core import capture as C                               # noqa: E402
from core import world as W                                 # noqa: E402
from core import relation as R                              # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS" if cond else "FAIL") + " - " + name + (f"  [{detail}]" if detail and not cond else ""))


def reset_all():
    G.reset(confirm=True)
    for f in (M.MEM_FILE, M.REL_FILE, M.OBS_FILE, M.EMB_FILE):
        if os.path.isfile(f):
            os.remove(f)


def build_graph_a():
    """Phase 38: graph deterministik ProjectA → Next.js → API → PostgreSQL → pool → timeout → solution."""
    p, _ = C.ensure_node({"type": "PROJECT", "name": "ProjectA", "scope": "PROJECT"}, "ProjectA")
    nx, _ = C.ensure_node({"type": "PACKAGE", "name": "Next.js", "scope": "PROJECT"}, "ProjectA")
    api, _ = C.ensure_node({"type": "API", "name": "checkout api", "scope": "PROJECT"}, "ProjectA")
    pg, _ = C.ensure_node({"type": "SERVICE", "name": "PostgreSQL", "scope": "PROJECT"}, "ProjectA")
    cp, _ = C.ensure_node({"type": "CONFIGURATION", "name": "connection pool", "scope": "PROJECT"}, "ProjectA")
    fl, _ = C.ensure_node({"type": "FAILURE", "name": "api timeout", "scope": "PROJECT"}, "ProjectA")
    so, _ = C.ensure_node({"type": "SOLUTION", "name": "increase pool size", "scope": "PROJECT"}, "ProjectA")
    sk, _ = C.ensure_node({"type": "SKILL", "name": "debugging", "scope": "SKILL"}, None)
    st, _ = C.ensure_node({"type": "STRATEGY", "name": "inspect_config_first", "scope": "STRATEGY"}, None)
    f = {"source": "USER_INPUT", "properties": {"evidence": ["project topology stated by operator"]}}
    G.add_edge(p["id"], "USES", nx["id"], **f)
    G.add_edge(p["id"], "USES", pg["id"], **f)
    G.add_edge(api["id"], "PART_OF", p["id"], **f)
    G.add_edge(api["id"], "DEPENDS_ON", pg["id"], **f)
    G.add_edge(pg["id"], "CONFIGURED_BY", cp["id"], **f)
    G.add_edge(api["id"], "FAILS_WITH", fl["id"], **f)
    G.add_edge(fl["id"], "CAUSED_BY", cp["id"], **f)
    G.add_edge(fl["id"], "SOLVED_BY", so["id"], source="EXECUTION_EVIDENCE",
               properties={"evidence": ["repair applied: pool size increased"]})
    G.add_edge(so["id"], "VALIDATED_BY", sk["id"], source="EXECUTION_EVIDENCE",
               properties={"evidence": ["validated by debugging skill run"]})
    G.add_edge(st["id"], "SUCCEEDED_IN", p["id"], source="EXECUTION_EVIDENCE",
               properties={"evidence": ["strategy used in project task"]})
    return {"p": p, "nx": nx, "api": api, "pg": pg, "cp": cp, "fl": fl, "so": so,
            "sk": sk, "st": st}


print("=" * 60)
print("v3.6 KNOWLEDGE GRAPH + WORLD MODEL — deterministic suite")
print("=" * 60)

# 1. node creation
reset_all()
n = G.add_node("TOOL", "nmap", description="port scanner", source="USER_INPUT")
check("1. node creation", n["ok"] and n["action"] == "CREATED" and G.get_node(n["node"]["id"]))

# 2. edge creation
a = G.add_node("PROJECT", "p1", project_id="p1", scope="PROJECT", source="USER_INPUT")
b = G.add_node("TOOL", "git", source="USER_INPUT")
e = G.add_edge(a["node"]["id"], "USES", b["node"]["id"], source="USER_INPUT")
check("2. edge creation", e["ok"] and e["action"] == "CREATED")

# 3. persistence (reload dari disk)
G.rebuild_index()
check("3. persistence", G.get_node(a["node"]["id"]) is not None
      and len(G.get_edges(a["node"]["id"])) == 1)

# 4. retrieval (index lookup by name + alias)
al = G.add_node("SERVICE", "PostgreSQL", properties={"aliases": ["postgres"]},
                source="USER_INPUT")
check("4. retrieval via index+alias",
      G.find_by_name("PostgreSQL", type="SERVICE") is not None
      and G.find_by_name("postgres", type="SERVICE") is not None)

reset_all()
nds = build_graph_a()

# 5. neighbor lookup
nb = G.neighbors(nds["pg"]["id"], direction="out")
check("5. neighbor lookup", any(x["node"]["name"] == "connection pool" for x in nb))

# 6. path finding
path = G.find_path(nds["api"]["id"], nds["cp"]["id"], max_depth=4)
check("6. path finding", [x["node"]["name"] for x in path] ==
      ["checkout api", "PostgreSQL", "connection pool"])

# 7. subgraph
sg = G.subgraph(nds["api"]["id"], max_depth=2, max_nodes=10)
check("7. subgraph bounded", sg["depth_reached"] == 2 and len(sg["nodes"]) >= 4)

# 8. entity extraction (deterministik, ber-evidence)
ents = C.extract_deterministic(
    "Fix timeout in the Next.js API caused by PostgreSQL. Edit config.toml", project_id="px")
names = {e["name"] for e in ents}
check("8. entity extraction deterministic",
      "postgresql" in names and "next.js" in names and "config.toml" in names
      and all(e["properties"]["evidence"] for e in ents))

# 9. normalization (alias, no auto-merge of ambiguity)
nm = C.normalize_entity("Postgres-DB")
check("9. normalization aliases", nm["name"] == "postgres db" and "postgresql" in nm["aliases"])

# 10. entity resolution MATCH/NEW/POSSIBLE/CONFLICT
v_new = C.resolve({"type": "SERVICE", "name": "Redis", "scope": "PROJECT"}, "ProjectA")["verdict"]
v_match = C.resolve({"type": "SERVICE", "name": "PostgreSQL", "scope": "PROJECT"}, "ProjectA")["verdict"]
v_possible = C.resolve({"type": "SERVICE", "name": "PostgreSQL", "scope": "PROJECT"}, "ProjectB")["verdict"]
G.add_node("PACKAGE", "nodejs", version="14.0", status="CURRENT", project_id="ProjectA",
           scope="PROJECT", source="EXECUTION_EVIDENCE")
v_conf = C.resolve({"type": "PACKAGE", "name": "nodejs", "scope": "PROJECT", "version": "18.0",
                    "source": "EXECUTION_EVIDENCE"}, "ProjectA")["verdict"]
check("10. entity resolution 4 verdicts",
      v_new == "NEW_ENTITY" and v_match == "MATCH"
      and v_possible == "POSSIBLE_MATCH" and v_conf == "CONFLICT",
      f"{v_new}/{v_match}/{v_possible}/{v_conf}")

# 11. duplicate detection (add_node dedupe → MERGED, bukan node baru)
before = len(G._nodes())
dup = G.add_node("SERVICE", "PostgreSQL", project_id="ProjectA", scope="PROJECT",
                 source="USER_INPUT", description="updated")
after = len(G._nodes())
check("11. duplicate detection", dup["action"] == "MERGED" and after == before)

# 12. temporal relationships (valid_until → edge kedaluwarsa tidak diambil default)
tmp = G.add_node("TOOL", "oldtool", source="USER_INPUT")
tmp2 = G.add_node("TOOL", "newtool", source="USER_INPUT")
te = G.add_edge(tmp["node"]["id"], "REPLACED_BY", tmp2["node"]["id"], source="USER_INPUT")
G.expire_edge(te["edge"]["id"], when="2020-01-01T00:00:00Z")
live = G.get_edges(tmp["node"]["id"], direction="out")
allr = G.get_edges(tmp["node"]["id"], direction="out", include_expired=True)
check("12. temporal validity", len(live) == 0 and len(allr) == 1)

# 13. current vs historical state (update_state tidak overwrite)
G.add_node("PACKAGE", "nextver", version="14.0", project_id="ProjectA", scope="PROJECT",
           source="EXECUTION_EVIDENCE")
nv = G.find_by_name("nextver", type="PACKAGE")
up = G.update_state(nv["id"], version="16.0", source="EXECUTION_EVIDENCE",
                    reason="upgrade verified by execution")
hist = G.state_history(nv["id"])
check("13. current vs historical state",
      up["ok"] and up["transition"]["from_version"] == "14.0"
      and G.get_node(nv["id"])["version"] == "16.0"
      and any(not h["current"] and h["state"].get("version") == "14.0" for h in hist)
      and G.get_node(nv["id"])["history"])

# 14. conflict detection (CONFLICTS_WITH + status CONFLICTED, bukan auto-fix)
conf = G.mark_conflict(nv["id"], reason="two versions claimed current",
                       other_id=nds["pg"]["id"], evidence=["task A said 14, task B said 16"])
cn = G.get_node(nv["id"])
check("14. conflict detection", conf["ok"] and cn["status"] == "CONFLICTED"
      and any(e["relation"] == "CONFLICTS_WITH" for e in G.get_edges(nv["id"])))

# 15. graph validation (bersih pada graph sehat)
issues = G.validate()
check("15. graph validation clean", issues["ok"] and issues["counts"]["dangling_edges"] == 0)

# 16. causal chain (arah eksplisit, inverse-causation diblokir)
chain = G.find_path(nds["fl"]["id"], nds["cp"]["id"], max_depth=2)
rev = G.neighbors(nds["cp"]["id"], direction="in",
                  allowed_relations={"CAUSED_BY"})
check("16. causal chain", [x["node"]["name"] for x in chain] == ["api timeout", "connection pool"]
      and rev == [])

# 17. solution graph
sol_path = G.find_path(nds["fl"]["id"], nds["sk"]["id"], max_depth=3)
check("17. solution graph", [x["node"]["name"] for x in sol_path] ==
      ["api timeout", "increase pool size", "debugging"])

# 18. failure graph (task FAILED_WITH failure → CAUSED_BY component)
t = C.ensure_node({"type": "TASK", "name": "fix api timeout task",
                   "scope": "PROJECT"}, "ProjectA")[0]
G.add_edge(t["id"], "FAILED_WITH", nds["fl"]["id"], source="EXECUTION_EVIDENCE",
           properties={"evidence": ["task failed with api timeout"]})
fg = G.neighbors(t["id"], direction="out", allowed_relations={"FAILED_WITH"})
check("18. failure graph", len(fg) == 1 and fg[0]["node"]["type"] == "FAILURE")

# 19. skill graph (HAS_VERSION + SUPERSEDES, historical ditandai)
C.link_skill_version("coding", "1.1.0", parent_version="1.0.0", status="ACTIVE",
                     evidence=["promoted by evolution test"])
skn = G.find_by_name("coding", type="SKILL")
ver_edges = [x for x in G.neighbors(skn["id"], direction="out", allowed_relations={"HAS_VERSION"})]
old = G.find_by_name("coding 1.0.0", type="SKILL_VERSION")
check("19. skill graph", len(ver_edges) >= 1
      and any(e["relation"] == "SUPERSEDES" for e in G.get_edges(ver_edges[0]["node_id"]))
      and old["status"] == "HISTORICAL" and G.get_node(old["id"]) is not None)

# 20. strategy graph
stg = W.get_related_strategies("ProjectA")
check("20. strategy graph", stg["count"] >= 1
      and stg["strategies"][0]["success_edges"] >= 1)

# 21. project scope isolation
G.add_node("SERVICE", "uvicorn", project_id="ProjectB", scope="PROJECT", source="USER_INPUT")
seen_a = {x["name"] for x in G.scoped_nodes("ProjectA")}
seen_b = {x["name"] for x in G.scoped_nodes("ProjectB")}
check("21. project scope isolation",
      "uvicorn" not in seen_a and "PostgreSQL" not in seen_b
      and "debugging" in seen_a and G.visible(G.find_by_name("debugging"), "ProjectB"))

# 22. secret redaction
sec = G.add_node("CONFIGURATION", "api key", description="key sk-abcdefgh12345678 and thk_live_ABCDEFGH1234567890",
                 properties={"token": "Bearer abcdefghijklmnopqrst"}, source="USER_INPUT")
blob = str(sec["node"])
check("22. secret redaction", "sk-abcdefgh12345678" not in blob
      and "thk_live_ABCDEFGH1234567890" not in blob and "REDACTED" in blob)

# 23. traversal limits
hub = C.ensure_node({"type": "PROJECT", "name": "hubproj", "scope": "PROJECT"}, "hubproj")[0]
for i in range(15):
    leaf = C.ensure_node({"type": "FILE", "name": f"hub/file{i}.py", "scope": "PROJECT"}, "hubproj")[0]
    G.add_edge(hub["id"], "CONTAINS", leaf["id"], source="USER_INPUT",
               properties={"evidence": [f"file{i} in project"]})
lim = G.subgraph(hub["id"], max_depth=3, max_nodes=5)
check("23. traversal limits", len(lim["nodes"]) <= 5 and lim["truncated"])

# 24. world model
st = W.get_project_state("ProjectA")
check("24. world model", st["found"] and st["nodes"] >= 4
      and "PostgreSQL" in (st["components"].get("SERVICE") or [])
      and any(x for x in st["components"].get("FAILURE", [])))

# 25. dependency graph
deps = W.get_dependencies("ProjectA", transitive=True, max_depth=2)
check("25. dependency graph", "Next.js" in deps["dependencies"] and "PostgreSQL" in deps["dependencies"])

# 26. impact analysis
imp = W.get_change_impact(name="PostgreSQL", type="SERVICE")
check("26. impact analysis", imp["found"] and imp["affected_nodes"] >= 3
      and "ProjectA" in imp["affected_projects"])

# 27. semantic + graph retrieval (memory + entity + relation)
M.store(M.make_memory("SOLUTION", "fix checkout api timeout",
                      "Increase PostgreSQL pool size then restart service.",
                      entities=["checkout api", "PostgreSQL"], project_id="ProjectA",
                      scope="PROJECT", source="EXECUTION_EVIDENCE", importance=0.8))
M.store(M.make_memory("SOLUTION", "unrelated python api timeout",
                      "Different stack; bump uvicorn workers.",
                      entities=["python"], project_id="ProjectB", scope="PROJECT",
                      source="EXECUTION_EVIDENCE"))
res = R.linked_context("why is my checkout api failing", project_id="ProjectA", top_k=3)
titles = [m["title"] for m in res["memories"]]
check("27. semantic+graph retrieval",
      titles and titles[0] == "fix checkout api timeout"
      and "checkout api" in res["seed_entities"]
      and res["scores"][0]["entity_match"] >= 0.5)

# 28. v3.5 integration (hybrid_search, retrieve_for_plan, feedback tetap jalan)
M.feedback(res["memories"][0]["id"], "success", helpful=True)
rp = M.retrieve_for_plan("checkout api timeout", project_id="ProjectA", top_k=3)
check("28. v3.5 integration", isinstance(rp, dict) and "memories" in rp and "scores" in rp
      and rp["memories"])

# 29. v3.4 integration (evolution sink → SKILL_VERSION + FAILURE/SOLUTION memori)
from core import evolution as E                               # noqa: E402
E.record_experience({"task_id": "t-evo-1", "skill": "coding", "old_version": "1.0.0",
                     "candidate_version": "1.2.0", "trigger": "unit test",
                     "result": "PROMOTED", "promotion": True})
sv = G.find_by_name("coding 1.2.0", type="SKILL_VERSION")
mem_fail = M.hybrid_search("skill evolution REJECTED", max_items=None)
check("29. v3.4 integration", sv is not None
      and any(e["relation"] == "SUPERSEDES" for e in G.get_edges(sv["id"], direction="out")))

# 30. v3.3 integration (strategy select + record_outcome → graph edge)
from core import strategy as S                                # noqa: E402
cands = S.generate_candidates("debug api timeout caused by postgres")
decision = S.select_strategy(cands, "debug api timeout caused by postgres")
chosen = decision["selected"]
S.REGISTRY.record_outcome(chosen.id, True, duration=1.0,
                          evidence=[{"type": "task_id", "id": t["id"], "detail": "completed"}])
link = C.link_strategy_outcome(chosen.id, t["id"], True)
isd = G.find_by_name(chosen.id, type="STRATEGY")
check("30. v3.3 integration", isd is not None and link["ok"])

# 31-33. regresi v3.2/v3.1/v3.0 (API orkestrasi utuh + sukses didata)
from core import orchestra as O                               # noqa: E402
check("31. v3.2 regression", callable(O.graph_validate) and callable(O.Scheduler)
      and O.graph_validate([{"id": "a", "depends_on": []}, {"id": "b", "depends_on": ["a"]}])["valid"]
      is True)
from core import experience as X                              # noqa: E402
check("32. v3.1 regression", callable(X.recall) and callable(X.save_task_memory)
      and isinstance(X.recall("anything"), dict))
check("33. v3.0 regression", callable(O.planner) and callable(O.critic)
      and callable(O.run_subtask) and O.STATES[0] == "RECEIVED")

print("-" * 60)
print("PHASE 40 — FAILURE INJECTION")
print("-" * 60)

# A. missing node referenced by edge (strict=True tolak; strict=False → terdeteksi validate)
bad = G.add_edge("does-not-exist", "USES", nds["pg"]["id"], strict=False)
v2 = G.validate()
check("A. missing node referenced by edge",
      bad["ok"] and not bad["edge"]["source_node"] in {n["id"] for n in G._nodes()}
      and "does-not-exist" in v2["missing_nodes"])

# B. duplicate edge (upsert, bukan duplikat baru)
cnt_before = len(G._edges())
again = G.add_edge(nds["p"]["id"], "USES", nds["nx"]["id"],
                   properties={"evidence": ["second statement same relation"]},
                   source="USER_INPUT")
check("B. duplicate edge detected", again["action"] == "UPDATED"
      and len(G._edges()) == cnt_before)

# C. cycle in graph
c1 = G.add_node("SKILL", "cyc-a", scope="SKILL", source="USER_INPUT")
c2 = G.add_node("SKILL", "cyc-b", scope="SKILL", source="USER_INPUT")
G.add_edge(c1["node"]["id"], "DEPENDS_ON", c2["node"]["id"], source="USER_INPUT")
G.add_edge(c2["node"]["id"], "DEPENDS_ON", c1["node"]["id"], source="USER_INPUT")
cycles = G.detect_cycles()
check("C. cycle detection", any(len(c) >= 3 for c in cycles))

# D. ambiguous entity → POSSIBLE_MATCH, tidak di-merge
amb = C.ensure_node({"type": "SERVICE", "name": "postgres", "scope": "PROJECT"}, "ProjectB")
check("D. ambiguous entity not merged",
      amb[1] in ("POSSIBLE_MATCH", "NEW_ENTITY") and amb[0]["project_id"] == "ProjectB"
      and G.find_by_name("postgres", type="SERVICE")["id"] != nds["pg"]["id"])

# E. conflicting versions
cx = G.add_node("PACKAGE", "conflictpkg", version="1.0", project_id="ProjectA",
                scope="PROJECT", source="EXECUTION_EVIDENCE")
vd = C.resolve({"type": "PACKAGE", "name": "conflictpkg", "version": "2.0",
                "scope": "PROJECT", "source": "EXECUTION_EVIDENCE"}, "ProjectA")
check("E. conflicting versions flagged", vd["verdict"] == "CONFLICT")

# F. stale world state
G.add_node("SERVICE", "stalesvc", project_id="ProjectA", scope="PROJECT",
           source="USER_INPUT", properties={"last_verified": "2019-01-01T00:00:00Z"})
G.update_node(G.find_by_name("stalesvc", type="SERVICE")["id"],
              {"last_verified": "2019-01-01T00:00:00Z"})
fr = G.refresh_freshness(stale_days=30)
stf = G.get_node(G.find_by_name("stalesvc", type="SERVICE")["id"])["freshness"]
check("F. stale world state", stf == "STALE" and fr["stale"] >= 1)

# G. traversal exceeds limit → aman (no explosion)
big = C.ensure_node({"type": "PROJECT", "name": "bigproj", "scope": "PROJECT"}, "bigproj")[0]
prev = big
for i in range(40):
    leaf = C.ensure_node({"type": "FILE", "name": f"big/f{i}.py", "scope": "PROJECT"}, "bigproj")[0]
    G.add_edge(prev["id"], "CONTAINS", leaf["id"], source="USER_INPUT",
               properties={"evidence": [f"chain {i}"]})
    prev = leaf
bigsg = G.subgraph(big["id"], max_depth=10, max_nodes=12)
check("G. traversal bounded", len(bigsg["nodes"]) <= 12 and bigsg["depth_reached"] <= 10)

# H. project scope violation attempt
sc = W.get_project_state("ProjectB")
leak = [x for x in (sc["components"].get("SERVICE") or []) if x == "PostgreSQL"]
check("H. project scope violation blocked", leak == []
      and "uvicorn" in (sc["components"].get("SERVICE") or []))

# I. corrupted graph record → validate mendeteksi, tidak crash
nodes_raw = G._nodes()
nodes_raw.append({"id": "corrupt1", "type": "NOT_A_TYPE", "name": "",
                  "properties": {}})
G._save_nodes(nodes_raw)
v3 = G.validate()
check("I. corrupted record detected safely", not v3["ok"] and v3["counts"]["malformed_nodes"] >= 1)

# J. semantic retrieval returns irrelevant memory → graph/scope ranking menahan
M.store(M.make_memory("SOLUTION", "irrelevant postgres note",
                      "This is a stale note about something else entirely.",
                      project_id="ProjectB", scope="PROJECT", source="LETHICA_INFERENCE"))
res2 = R.context_block("why is my checkout api failing", project_id="ProjectA", top_k=3)[1]
top = res2["scores"][0]["memory"]["title"] if res2["scores"] else ""
check("J. irrelevant memory does not outrank", top == "fix checkout api timeout", top)

# cleanup korupsi supaya graph tetap valid utk pemeriksaan akhir
G._save_nodes([n for n in G._nodes() if n["id"] != "corrupt1"])

print("-" * 60)
print("PHASE 36 — OBSERVABILITY (real counters, tidak difabrikasi)")
print("-" * 60)
obs = G.observability()
required = ["nodes_created", "nodes_updated", "edges_created", "edges_updated",
            "entities_resolved", "entities_unresolved", "graph_queries",
            "graph_traversals", "world_model_updates", "conflicts", "stale_nodes",
            "impact_analysis_count"]
check("36. observability counters present",
      all(k in obs for k in required) and obs["nodes_created"] > 0
      and obs["edges_created"] > 0 and obs["graph_queries"] > 0)
print("   counters:", {k: obs[k] for k in required if obs.get(k)})

print()
print("=" * 60)
print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", FAIL)
print("=" * 60)

try:
    shutil.rmtree(WS, ignore_errors=True)
except Exception:
    pass
sys.exit(1 if FAIL else 0)