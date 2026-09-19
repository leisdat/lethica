import core.memory as M

print("LOAD OK")
m1 = M.store(M.make_memory(
    "SOLUTION", "fix playwright timeout",
    "Increase navigation timeout and wait for network idle.",
    tags=["web", "playwright"], project_id="projA",
    source="EXECUTION_EVIDENCE", importance=0.8,
    metadata={"evidence": "3 successful tasks"}))
m2 = M.store(M.make_memory(
    "LESSON", "api needs auth",
    "API X requires auth before endpoint Y.",
    tags=["api", "auth"], project_id="projA",
    source="EXECUTION_EVIDENCE", scope="GLOBAL"))
m3 = M.store(M.make_memory(
    "FACT", "db timeout 30s",
    "DB connection timeout is 30 seconds.",
    entities=["db_timeout"], source="USER_INPUT"))
m4 = M.store(M.make_memory(
    "FACT", "db timeout 60s",
    "DB connection timeout is 60 seconds.",
    entities=["db_timeout"], source="USER_INPUT"))
print("stored:", m1["id"], m2["id"], m3["id"], m4["id"])

res = M.retrieve_for_plan(
    "Browser automation hangs while waiting for page load",
    project_id="projA")
top = res["similar_tasks"][0]
print("HYBRID TOP:", top["title"], "rel=", top["relevance"], "type=", top["type"])

cf = M.detect_conflict()
print("CONFLICTS:", len(cf), (cf[0]["note"] if cf else "none"))

M.feedback(m1["id"], "success")
print("m1 quality after success feedback:", M.get(m1["id"])["quality"])

# project isolation: query with different project should not dominate
res2 = M.retrieve_for_plan("increase navigation timeout", project_id="projB")
t2 = res2["similar_tasks"][0]
print("ISOLATION projB top:", t2["title"], "rel=", t2["relevance"])

# secret redaction test
m5 = M.store(M.make_memory("KNOWLEDGE", "key leak", "my api key is sk-abcdefghijklmnopqrstuvwxyz123456"))
print("REDACTED:", "[REDACTED:secret]" in m5["content"])

# consolidation
c = M.consolidate()
print("CONSOLIDATED groups:", c)

print("OBS:", {k: v for k, v in M.observability().items() if v})
print("ALL OK")
