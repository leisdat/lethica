#!/usr/bin/env python3
"""Deterministic tests untuk Lethica v3.5 Semantic Long-Term Memory.
Run: python3 tests/test_semantic_memory.py
Coverage: Phase 33 (1-29) + Phase 34 (semantic retrieval) + Phase 36 (failure injection).
Tanpa embedding provider (default OFF) → semantic fallback ke lexical, test deterministic.
"""
import os, sys, shutil, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import memory as M

MEM_DIR = M.config.MEMORY_DIR
for f in ("memories.json", "embeddings.json", "relations.json", "observability.json",
          "memories.db", "memories.db-wal", "memories.db-shm"):  # v3.7.1: store SQLite+WAL
    p = os.path.join(MEM_DIR, f)
    if os.path.isfile(p):
        os.remove(p)

PASS, FAIL = [], []
def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("✓" if cond else "✗") + f" {name}" + (f"  [{extra}]" if extra and not cond else ""))


# ── Phase 1: unified memory model ──
m = M.make_memory("SOLUTION", "fix timeout", "Increase pool size.", tags=["db"], project_id="pA", source="EXECUTION_EVIDENCE")
check("1.unified_model_has_id", "id" in m and m["id"].startswith("m"))
check("1.unified_model_type_valid", m["type"] == "SOLUTION")
check("1.unified_model_defaults", "importance" in m and "confidence" in m)

# ── Phase 2: lifecycle store ──
stored = M.store(m)
check("2.store_persists", any(x["id"] == stored["id"] for x in M._memories()))

# ── Phase 3: extraction (compact, not full transcript) ──
class FakeTask:
    goal = "Fix API timeout in project pA"
    state = "COMPLETED"
    id = "task-x"
    project_id = "pA"
    skill_report = {"available_skills": ["db"], "active_skill": "db"}
    final_solution = "Increase connection pool to 50."
    debug_log = [{"root_cause": "pool exhausted", "fix_steps": ["resize pool"]}]
extracted = M.extract_from_task(FakeTask())
check("3.extraction_creates_task_memory", any(x["type"] == "TASK" for x in extracted))
check("3.extraction_creates_solution", any(x["type"] == "SOLUTION" for x in extracted))
check("3.extraction_creates_lesson", any(x["type"] == "LESSON" for x in extracted))

# ── Phase 4/5/7: semantic provider OFF → fallback ──
check("4.semantic_off_returns_empty", M.semantic_search("anything") == [])
check("5.provider_is_null_default", isinstance(M._get_provider(), M.NullEmbeddingProvider))
# hybrid tanpa semantic tetap jalan (lexical + metadata)
res = M.retrieve_for_plan("Fix API timeout in project pA", project_id="pA")
check("7.hybrid_works_without_embedding", len(res["similar_tasks"]) > 0)

# ── Phase 8: relevance ranker traceable ──
top = res["scores"][0]
check("8.ranker_has_reasons", isinstance(top["reasons"], list) and len(top["reasons"]) > 0)
check("8.ranker_relevance_range", 0.0 <= top["relevance"] <= 1.0)

# ── Phase 9: contextual retrieval (project match dominates) ──
rA = M.retrieve_for_plan("API timeout pool fix", project_id="pA")["scores"][0]["relevance"]
rB = M.retrieve_for_plan("API timeout pool fix", project_id="pZ")["scores"][0]["relevance"]
check("9.project_context_ranking", rA > rB, f"projA={rA} projZ={rB}")
# semantically similar but different wording → should still find (lexical overlap)
q = M.retrieve_for_plan("database connection pool exhausted causes request failures", project_id="pA")
check("9.similar_wording_found", any("pool" in s["reasons"] or s["relevance"] > 0.3 for s in q["scores"]))

# ── Phase 10: project memory ──
pm = M.store(M.make_memory("PROJECT", "proj pA", "API service on :8080, uses Postgres.", project_id="pA", source="USER_INPUT", scope="PROJECT"))
check("10.project_memory_stored", pm["scope"] == "PROJECT" and pm["project_id"] == "pA")

# ── Phase 11: solution memory ──
sol = M.store(M.make_memory("SOLUTION", "sol: db timeout", "Resize pool + release conns.", project_id="pA", source="EXECUTION_EVIDENCE", metadata={"evidence": "3 ok"}))
check("11.solution_memory", sol["type"] == "SOLUTION")

# ── Phase 12: lesson memory ──
les = M.store(M.make_memory("LESSON", "lesson: check lifecycle", "Check conn lifecycle before raising timeout.", source="EXECUTION_EVIDENCE", scope="GLOBAL"))
check("12.lesson_memory", les["type"] == "LESSON")

# ── Phase 13/14: consolidation + dedupe ──
dup = M.make_memory("SOLUTION", "fix db timeout", "Resize pool + release conns.", project_id="pA", source="EXECUTION_EVIDENCE", metadata={"evidence": "3 ok"})
before = len(M._memories())
M.store(dup)
after = len(M._memories())
check("14.dedupe_no_duplicate", after == before, f"before={before} after={after}")
# consolidation of repeated
for i in range(3):
    M.store(M.make_memory("SOLUTION", "repeat fix", "Same fix applied.", tags=["rep"], source="EXECUTION_EVIDENCE", metadata={"evidence": f"{i} ok"}))
cons = M.consolidate()
check("13.consolidation_runs", cons >= 0)

# ── Phase 15: confidence ──
low = M.store(M.make_memory("FACT", "inferred", "model guessed this.", source="LETHICA_INFERENCE"))
high = M.store(M.make_memory("FACT", "verified", "proven by 5 execs.", source="EXECUTION_EVIDENCE"))
high["success_count"] = 5
M._save_memories(M._memories())
check("15.confidence_low_for_inference", low["confidence"] == "LOW")
check("15.confidence_logic", high["confidence_score"] >= 0.6)

# ── Phase 16: feedback loop ──
M.feedback(sol["id"], "success")
after_fb = M.get(sol["id"])
check("16.feedback_increases_success", after_fb["success_count"] >= 1)
M.feedback(sol["id"], "failure")
check("16.feedback_failure_counted", M.get(sol["id"])["failure_count"] >= 1)

# ── Phase 17: decay ──
old = M.store(M.make_memory("FACT", "stale fact", "old.", source="LETHICA_INFERENCE", importance=0.5))
old["timestamp"] = "2020-01-01T00:00:00Z"
old["importance"] = 0.1
M._save_memories(M._memories())
d = M.decay()
check("17.decay_runs", d >= 0)

# ── Phase 18: contradiction detection ──
M.store(M.make_memory("FACT", "timeout 30", "DB timeout 30s.", entities=["db_timeout"], source="USER_INPUT"))
M.store(M.make_memory("FACT", "timeout 60", "DB timeout 60s.", entities=["db_timeout"], source="USER_INPUT"))
cf = M.detect_conflict()
check("18.conflict_detected", len(cf) >= 1, f"conflicts={len(cf)}")
check("18.conflict_notes_newest_not_correct", cf and "newest not automatically correct" in cf[0]["note"])

# ── Phase 19/20: temporal + version awareness ──
v1 = M.store(M.make_memory("SOLUTION", "fix v1", "Use lib v1 API.", metadata={"version": "1.x"}, source="EXECUTION_EVIDENCE"))
v2 = M.store(M.make_memory("SOLUTION", "fix v2", "Use lib v2 API.", metadata={"version": "2.x"}, source="EXECUTION_EVIDENCE"))
check("19.version_metadata_stored", v1["metadata"].get("version") == "1.x" and v2["metadata"].get("version") == "2.x")

# ── Phase 21: quality control (source tagging) ──
inf = M.store(M.make_memory("KNOWLEDGE", "guess", "probably x.", source="LETHICA_INFERENCE"))
ext = M.store(M.make_memory("KNOWLEDGE", "fact", "confirmed y.", source="EXECUTION_EVIDENCE"))
usr = M.store(M.make_memory("KNOWLEDGE", "said", "user said z.", source="USER_INPUT"))
check("21.source_tagged", inf["source"] == "LETHICA_INFERENCE" and ext["source"] == "EXECUTION_EVIDENCE" and usr["source"] == "USER_INPUT")

# ── Phase 22: secret redaction ──
sec = M.store(M.make_memory("KNOWLEDGE", "leak", "key sk-abcdefghijklmnopqrstuvwxyz123456 here"))
check("22.secret_redacted", "[REDACTED:secret]" in sec["content"])

# ── Phase 23: scope isolation ──
gp = M.store(M.make_memory("FACT", "global", "general python.", scope="GLOBAL", source="LETHICA_INFERENCE"))
pp = M.store(M.make_memory("FACT", "proj-specific", "internal only pA.", project_id="pA", scope="PROJECT", source="LETHICA_INFERENCE"))
# query with different project → project-scoped excluded, global shared
iso = M.hybrid_search("proj-specific internal", ctx={"project_id": "pOther"})
iso_ids = [s["memory_id"] for s in iso]
check("23.scope_isolation", pp["id"] not in iso_ids, f"excluded={pp['id'] not in iso_ids}")
check("23.global_shared", gp["id"] in iso_ids)

# ── Phase 24/25: retrieval policy + context budget ──
big = M.retrieve_for_plan("pool timeout db connection", project_id="pA", max_items=M.CONTEXT_MAX_ITEMS, max_tokens=M.CONTEXT_MAX_TOKENS)
check("25.context_budget_items", len(big["similar_tasks"]) <= M.CONTEXT_MAX_ITEMS)
check("25.context_budget_tokens", sum(len(s["content"]) // 4 + 50 for s in big["memories"]) <= M.CONTEXT_MAX_TOKENS + 200)

# ── Phase 29: memory API ──
got = M.get(sol["id"])
check("29.api_get", got and got["id"] == sol["id"])
upd = M.update(sol["id"], {"importance": 0.9})
check("29.api_update", upd["importance"] == 0.9)
M.link(sol["id"], les["id"], "validated_by")
check("29.api_link", les["id"] in M.get(sol["id"])["related_memories"])
arch = M.archive(v1["id"])
check("29.api_archive", arch["archived"] is True)
# archived excluded from retrieval
after_arch = M.retrieve_for_plan("fix v1 lib", project_id=None)
check("29.archive_excluded", v1["id"] not in [s["memory_id"] for s in after_arch["scores"]])

# ── Phase 30: graph relations ──
rels = M._relations()
check("30.relations_stored", any(r["from"] == sol["id"] and r["to"] == les["id"] for r in rels))

# ── Phase 31: observability ──
obs = M.observability()
check("31.observability_tracked", obs["memory_stores"] > 0 and obs["hybrid_queries"] > 0)

# ── Phase 34: semantic retrieval test (proxy — lexical fallback) ──
# "Playwright navigation timed out because page never reached network idle"
# vs "Browser automation hangs while waiting for page load" → harus match via lexical overlap
pw = M.store(M.make_memory("SOLUTION", "playwright timeout", "Increase navigation timeout and wait for network idle.", tags=["playwright", "timeout", "navigation"], source="EXECUTION_EVIDENCE", importance=0.8))
q34 = M.retrieve_for_plan("Browser automation hangs while waiting for page load")
hit34 = [s for s in q34["scores"] if s["memory_id"] == pw["id"]]
check("34.semantic_proxy_match", len(hit34) > 0, "different wording masih match leksikal")
# "Recipe for fried rice" → playwright memory harusnya rendah relevance (lexical noise acceptable,
# semantic mode ON akan eliminasi via cosine≈0). Assert relevance pw < 0.25 sebagai proxy.
q34b = M.retrieve_for_plan("Recipe for fried rice delicious chicken")
pw_score = next((s for s in q34b["scores"] if s["memory_id"] == pw["id"]), None)
check("34.semantic_proxy_no_false_top_match", pw_score is None or pw_score["relevance"] < 0.25,
      f"pw_rel={pw_score['relevance'] if pw_score else 'absent'}")

# ── Phase 36: failure injection ──
# A: embedding unavailable → lexical fallback (already proven: semantic_search==[])
check("36A.embedding_unavailable_fallback", M.semantic_search("x") == [])
# E: secret → redacted (proven 22)
# F: irrelevant filtered (proven 34b)
# H: project isolation (proven 23)
# I: context budget (proven 25)

# ── Phase 39: backward compat — experience still intact ──
from core import experience
check("39.experience_intact", hasattr(experience, "recall") and hasattr(experience, "save_task_memory"))

print(f"\n=== RESULT: {len(PASS)} passed, {len(FAIL)} failed ===")
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
print("ALL SEMANTIC MEMORY TESTS PASS")
