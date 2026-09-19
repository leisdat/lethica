#!/usr/bin/env python3
"""Deterministic v3.3 Adaptive Planning tests; no live LLM or executor."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import strategy
from core import orchestra


def ok(condition, message):
    if not condition:
        raise AssertionError(message)
    print("PASS -", message)


def main():
    with tempfile.TemporaryDirectory() as td:
        path = os.path.join(td, "strategy-registry.json")
        reg = strategy.StrategyRegistry(path)
        s = strategy.Strategy(id="probe", name="Probe", task_patterns=["api"],
                              execution_style="sequential")
        reg.register(s)
        ok(reg.get("probe").name == "Probe", "strategy creation + retrieval")
        ok(os.path.isfile(path), "registry persistence")
        reg.record_usage("probe", [{"type": "task_id", "id": "t1"}])
        reg.record_outcome("probe", True, duration=2, cost=3,
                           evidence=[{"type": "task_id", "id": "t1"}])
        got = reg.get("probe")
        ok(got.sample_count == 1 and got.success_count == 1 and got.evidence,
           "usage/outcome/evidence persistence")
        for _ in range(2):
            reg.record_outcome("probe", True)
        ok(reg.get("probe").status == "HEALTHY", "strategy recovery to HEALTHY")
        for _ in range(3):
            reg.record_outcome("probe", False)
        ok(reg.get("probe").status in ("DEGRADED", "BROKEN"),
           "strategy degradation after recent failures")
        reg.mark_inactive("probe")
        ok(reg.get("probe").status == "INACTIVE", "inactive state retained")

    ok(strategy.classify_complexity("create hello.txt") == "TRIVIAL",
       "trivial complexity classification")
    trivial = strategy.generate_candidates("create hello.txt")
    ok(len(trivial) == 1 and trivial[0].id == "direct", "trivial task uses one direct strategy")
    complex_candidates = strategy.generate_candidates(
        "Investigate why API requests are timing out and compare configuration logs", "COMPLEX", 4)
    ok(2 <= len(complex_candidates) <= 4, "complex task generates bounded candidates")
    ok(len({x.id for x in complex_candidates}) == len(complex_candidates),
       "candidate ids are unique")

    # Isolated registry for evidence/confidence assertions.
    old_reg = strategy.REGISTRY
    try:
        with tempfile.TemporaryDirectory() as td:
            strategy.REGISTRY = strategy.StrategyRegistry(os.path.join(td, "r.json"))
            cands = strategy.generate_candidates("Investigate API timeout", "COMPLEX", 4)
            decision = strategy.select_strategy(cands, "Investigate API timeout",
                failures=[{"id": "f1", "context": "research_first", "root_cause": "version mismatch"}],
                skill_report={"available_skills": ["debug"]}, task_id="fixed-no-explore")
            ok(decision["selected"] is not None and decision["evidence_level"] == "LOW",
               "selection returns evidence and low confidence for tiny samples")
            ok(decision["confidence"] == "LOW", "low-sample confidence protection")
            ok(decision["selected"].id in ("execute_first", "inspect_config_first"),
               "task fit and known failure influence selection")
            for _ in range(3):
                strategy.REGISTRY.record_outcome("execute_first", True)
            strong = strategy.select_strategy(cands, "Investigate API timeout",
                skill_report={"available_skills": ["debug"]}, task_id="fixed-no-explore")
            ok(strong["confidence"] == "HIGH", "confidence rises only after minimum samples")
            broken_skills = strategy.select_strategy(cands, "Investigate API timeout",
                skill_report={"missing_skills": ["debug"]}, task_id="fixed-no-explore")
            ok(broken_skills["selected"] is not None and
               "missing" in " ".join(broken_skills["reasoning"]),
               "skill health/missing evidence penalizes candidates")
            # Exploration is bounded and deterministic: budget 0 always exploits.
            old_cfg = strategy.config.CFG
            strategy.config.CFG = dict(old_cfg)
            strategy.config.CFG["adaptive_planning"] = {"exploration_enabled": True,
                "exploration_budget": 0.0, "min_evidence_samples": 3, "max_candidates": 4}
            no_explore = strategy.select_strategy(cands, "Investigate API timeout", task_id="x")
            ok(no_explore["explored"] is False, "exploration budget is bounded")
            strategy.config.CFG = old_cfg
    finally:
        strategy.REGISTRY = old_reg

    graph = orchestra.graph_validate([
        {"id": "research", "depends_on": []},
        {"id": "inspect", "depends_on": ["research"]},
        {"id": "test", "depends_on": ["inspect"]},
    ])
    ok(graph["valid"] and graph["order"] == ["research", "inspect", "test"],
       "strategy DAG conversion remains compatible with v3.2 validator")
    cycle = orchestra.graph_validate([
        {"id": "a", "depends_on": ["b"]}, {"id": "b", "depends_on": ["a"]}])
    ok(not cycle["valid"] and cycle["cycle"], "DAG cycle protection remains authoritative")

    # Failure injection: fallback switches once, never revisits a tried strategy.
    old_reg = strategy.REGISTRY
    old_serial, old_merge = orchestra._execute_serial, orchestra.merge_results
    try:
        with tempfile.TemporaryDirectory() as td:
            strategy.REGISTRY = strategy.StrategyRegistry(os.path.join(td, "r.json"))
            task = orchestra.Task("Investigate API timeout", client=None)
            task.messages = []
            task.plan = {"subtasks": [{"id": "s1", "description": "inspect API",
                                        "depends_on": [], "required_skills": [],
                                        "required_tools": []}]}
            task.skill_report = {"available_skills": []}
            task.strategy_candidates = strategy.generate_candidates(task.goal, "COMPLEX", 3)
            task.strategy = task.strategy_candidates[0]
            task.strategy_history = [task.strategy.id]
            task.critic = {"status": "fail", "bugs": ["timeout"],
                           "requirements_failed": ["timeout"], "recommendation": "repair"}
            orchestra._execute_serial = lambda *_a, **_k: None
            orchestra.merge_results = lambda *_a, **_k: None
            first = orchestra._switch_strategy(task)
            second_id = task.strategy.id
            ok(first and task.strategy_switches == 1 and second_id not in
               [task.strategy_history[0]], "failure injection switches to bounded fallback")
            task.strategy_candidates = [s for s in task.strategy_candidates
                                        if s.id in task.strategy_history]
            ok(not orchestra._switch_strategy(task), "oscillation prevention blocks exhausted fallback")
    finally:
        orchestra._execute_serial, orchestra.merge_results = old_serial, old_merge
        strategy.REGISTRY = old_reg

    print("RESULT: V3.3 ADAPTIVE TESTS GREEN")


if __name__ == "__main__":
    main()
