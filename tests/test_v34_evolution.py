#!/usr/bin/env python3
"""Deterministic v3.4 skill evolution tests; no LLM/network."""
import json
import os
import tempfile
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config, evolution, registry, tools, orchestra


def ok(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS -", message)


def main():
    old = (registry.REG_FILE, tools.SKILL_DIR, evolution.STORE,
           evolution.SNAPSHOT_DIR, evolution.CANDIDATE_DIR, config.LETHICA_DIR)
    with tempfile.TemporaryDirectory() as td:
        reg_path = os.path.join(td, "skill-registry.json")
        skill_dir = os.path.join(td, "skills")
        os.makedirs(skill_dir)
        registry.REG_FILE = reg_path
        tools.SKILL_DIR = skill_dir
        evolution.STORE = evolution.EvolutionStore(os.path.join(td, "evolution.json"))
        evolution.SNAPSHOT_DIR = os.path.join(td, "snapshots")
        evolution.CANDIDATE_DIR = os.path.join(td, "candidates")
        config.LETHICA_DIR = td
        tools._SKILL_INDEX = {}

        # Seed an active baseline directly through the existing registry abstraction.
        base_dir = os.path.join(skill_dir, "testing", "assert-skill")
        os.makedirs(base_dir)
        base_path = os.path.join(base_dir, "SKILL.md")
        with open(base_path, "w", encoding="utf-8") as fh:
            fh.write("# assert-skill\n\n## Purpose\nassert testing\n")
        tools._SKILL_INDEX = {"testing/assert-skill": base_path}
        registry._save_raw({"version": 1, "skills": {
            "testing/assert-skill": {
                "name": "testing/assert-skill", "version": 1,
                "description": "assert testing", "capabilities": ["assert_testing"],
                "dependencies": [], "tools": [], "examples": [], "tests": [],
                "confidence": 0.9, "success_rate": 0.95, "usage_count": 10,
                "failure_count": 0, "last_used": None, "last_verified": None,
                "status": "verified", "success_count": 10, "recent": [1] * 10,
                "failure_streak": 0, "test_pass_rate": 1.0}}})

        # 1-4: proposal, capability matching, duplicate prevention, gap detection.
        gaps = evolution.detect_gaps("t-gap", ["assert_testing", "missing_capability"])
        ok(gaps[0].recommended_action == "USE_EXISTING", "healthy capability gap uses existing skill")
        ok(gaps[1].recommended_action == "CREATE_NEW", "missing capability creates a gap, not a blind skill")
        duplicate = evolution.propose(evolution.SkillProposal(
            "better_assert", "same", ["assert_testing"], mode="CREATE"), "t1")
        ok(duplicate["action"] == "USE_EXISTING" and duplicate["duplicates"],
           "duplicate capability prevented")
        proposal = evolution.SkillProposal(
            "assert-skill", "improved assert helper", ["assert_testing"],
            test_plan=["python3 -c 'print(1)'"], mode="IMPROVE")
        ok(evolution.classify_risk(proposal) == "LOW", "risk classification LOW")
        ok(evolution.dependency_analysis(proposal)["available"], "dependency analysis available")

        # 5-8: immutable lineage, snapshot, candidate, rollback.
        evolution.STORE.record("testing/assert-skill", {
            "version": "1.0.0", "parent_version": None, "created_at": evolution._now(),
            "status": "ACTIVE", "implementation": base_dir, "capabilities": ["assert_testing"],
            "tests": [], "evidence": []})
        evolution.STORE.set_active("testing/assert-skill", "1.0.0")
        snap = evolution.create_snapshot("testing/assert-skill", "1.0.0")
        ok(snap["ok"] and os.path.isfile(os.path.join(snap["path"], "SKILL.md")),
           "snapshot creation")
        built = evolution.build_candidate(proposal, "# candidate\n\n## Purpose\nimproved", "t2", "known failure")
        ok(built["ok"] and built["version"] == "1.0.1" and built["parent_version"] == "1.0.0",
           "candidate version and lineage")
        ok(len(evolution.STORE.versions("testing/assert-skill")) == 2,
           "version history is immutable")
        with open(base_path, "w", encoding="utf-8") as fh: fh.write("CORRUPTED")
        rolled = evolution.rollback("testing/assert-skill", built["version"], snap, "injected failure")
        ok(rolled["ok"] and open(base_path, encoding="utf-8").read().startswith("# assert-skill"),
           "deterministic rollback restores snapshot")
        ok(next(v for v in evolution.STORE.versions("testing/assert-skill")
                if v["version"] == built["version"])["status"] == "REJECTED",
           "failed candidate retained as REJECTED")

        # 9-15: pass/reject, baseline, dependency, budget, canary.
        good = evolution.build_candidate(proposal, "# good", "t3")
        ev = evolution.evaluate_candidate("testing/assert-skill", good["version"],
                                          ["python3 -c 'print(1)'"], baseline={"success_rate": 0.5})
        ok(ev["recommendation"] == "PROMOTE" and ev["tests_passed"] == 1,
           "candidate test + objective evaluation promotes")
        canary = evolution.run_canary("testing/assert-skill", good["version"],
                                      lambda *_: True)
        ok(canary["ok"] and canary["tasks"] == 3, "bounded canary success")
        promoted = evolution.promote("testing/assert-skill", good["version"], snap, canary)
        ok(promoted["ok"] and evolution.STORE.skill("testing/assert-skill")["active_version"] == good["version"],
           "verified candidate promotion")
        bad = evolution.build_candidate(proposal, "# bad", "t4")
        bad_eval = evolution.evaluate_candidate("testing/assert-skill", bad["version"],
                                                 ["python3 -c 'import sys; sys.exit(1)'"],
                                                 baseline={"success_rate": 1.0})
        ok(bad_eval["recommendation"] == "REJECT" and bad_eval["tests_failed"] == 1,
           "candidate failure and regression rejected")
        missing_dep = evolution.propose(evolution.SkillProposal(
            "new", "new", ["new_cap"], dependencies=["does-not-exist"]), "t5")
        ok(missing_dep["action"] == "REJECT", "missing dependency rejected")
        disabled = evolution.config.CFG
        evolution.config.CFG = dict(disabled)
        evolution.config.CFG["skill_evolution"] = {"enabled": False}
        budget_result = evolution.build_candidate(evolution.SkillProposal(
            "budgeted", "x", ["new_cap"], mode="CREATE"), "# x", "t-budget")
        ok(budget_result["action"] == "ABORT", "evolution budget/disabled gate is bounded")
        evolution.config.CFG = disabled
        canary_candidate = evolution.build_candidate(proposal, "# canary", "t5-canary")
        canary_eval = evolution.evaluate_candidate("testing/assert-skill", canary_candidate["version"],
                                                   ["python3 -c 'print(1)'"], baseline={"success_rate": 0.5})
        fail_canary = evolution.run_canary("testing/assert-skill", canary_candidate["version"],
                                           lambda *_: False)
        ok(not fail_canary["ok"] and fail_canary["recommendation"] == "ROLLBACK",
           "canary failure triggers rollback recommendation")

        # 16-20: lifecycle, learning, classifier, v3.3 integration.
        history = evolution.record_experience({"task_id": "t3", "skill": "testing/assert-skill",
            "old_version": "1.0.0", "candidate_version": good["version"],
            "trigger": "known failure", "evaluation": ev, "promotion": promoted})
        saved = json.load(open(os.path.join(td, "skill-evolution-history.json")))
        ok(history["task_id"] == "t3" and saved[-1]["candidate_version"] == good["version"],
           "evolution experience persisted")
        ok(evolution.classify_failure(skill_failed=True) == "SKILL_FAILURE" and
           evolution.classify_failure(strategy_failed=True) == "STRATEGY_FAILURE" and
           evolution.classify_failure(environment_failed=True) == "ENVIRONMENT_FAILURE",
           "strategy/skill/environment failure distinction")
        task = orchestra.Task("use assert testing", client=None)
        task.messages = []
        task.plan = {"subtasks": [{"id": "s1", "description": "run assert", "required_skills": ["assert_testing"]}]}
        task.skill_report = None
        report = orchestra.skill_analyst(task)
        ok(task.skill_gaps and task.skill_gaps[0].capability_required == "assert_testing",
           "v3.3 Skill Analyst exposes v3.4 capability gap")
        ok(report["action"] in ("EXECUTE", "EXECUTE_WITH_CAUTION"),
           "v3.3 skill analysis compatibility")

        full = evolution.evolve(
            "t-full", evolution.SkillProposal(
                "evolve-demo", "disposable lifecycle skill", ["evolve_demo"],
                test_plan=["python3 -c 'print(\"evolve-ok\")'"], mode="CREATE"),
            "# evolve-demo\n\n## Purpose\ndisposable lifecycle skill",
            ["python3 -c 'print(\"evolve-ok\")'"],
            runner=lambda *_: True, reason="failure-driven proposal")
        ok(full["ok"] and full["action"] == "PROMOTE" and
           full["evaluation"]["recommendation"] == "PROMOTE",
           "full propose→build→test→evaluate→canary→promote lifecycle")

    (registry.REG_FILE, tools.SKILL_DIR, evolution.STORE, evolution.SNAPSHOT_DIR,
     evolution.CANDIDATE_DIR, config.LETHICA_DIR) = old
    print("RESULT: V3.4 EVOLUTION TESTS GREEN")


if __name__ == "__main__":
    main()
