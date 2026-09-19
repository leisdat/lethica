"""v3.4 controlled, versioned skill evolution.

This module is an approval pipeline around the existing Skill Registry. It never
edits an active verified skill during candidate creation: candidates live in a
separate workspace, are tested through the existing sandbox, and are promoted
only through an explicit evidence gate. Failed candidates remain in lineage.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

from core import config, registry, tools

STATUSES = ("DRAFT", "UNVERIFIED", "TESTING", "VERIFIED", "ACTIVE",
            "DEGRADED", "BROKEN", "DEPRECATED", "REJECTED")
MODES = ("CREATE", "IMPROVE", "REPAIR", "ADAPT", "MIGRATE")
RISKS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
EVOLUTION_FILE = os.path.join(config.LETHICA_DIR, "skill-evolution.json")
SNAPSHOT_DIR = os.path.join(config.WORKSPACE, "evolution", "snapshots")
CANDIDATE_DIR = os.path.join(config.WORKSPACE, "evolution", "candidates")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
        return value
    except (OSError, ValueError, TypeError):
        return copy.deepcopy(default)


def _save(path, value):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


def _norm(value):
    return re.sub(r"[^a-z0-9]+", "_", (value or "").lower()).strip("_")


def _version_parts(version):
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", str(version or "0.0.0"))
    return tuple(map(int, m.groups())) if m else (0, 0, 0)


def next_version(versions, mode="IMPROVE"):
    """Deterministic semver candidate version; existing versions are immutable."""
    current = max((_version_parts(v) for v in versions), default=(0, 0, 0))
    major, minor, patch = current
    if not versions:
        return "1.0.0"
    if mode in ("CREATE", "MIGRATE"):
        return f"{major + 1}.0.0" if major else "1.0.0"
    if mode == "ADAPT":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


@dataclass
class EvolutionBudget:
    enabled: bool = True
    max_candidates_per_task: int = 1
    max_repair_iterations: int = 2
    max_research_calls: int = 5
    max_build_attempts: int = 2
    max_test_attempts: int = 3
    max_canary_tasks: int = 3
    max_canary_failures: int = 1

    @classmethod
    def load(cls):
        raw = config.CFG.get("skill_evolution", {})
        values = {k: raw.get(k, getattr(cls, k)) for k in cls.__dataclass_fields__}
        for key in values:
            if key != "enabled":
                values[key] = max(0, int(values[key]))
        values["enabled"] = bool(values["enabled"])
        return cls(**values)


@dataclass
class SkillGap:
    task_id: str
    capability_required: str
    matching_skills: list[str] = field(default_factory=list)
    missing_capabilities: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    severity: str = "MEDIUM"
    recommended_action: str = "RESEARCH_MORE"

    def to_dict(self):
        return asdict(self)


@dataclass
class SkillProposal:
    name: str
    purpose: str
    capabilities: list[str]
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    security_level: str = "LOW"
    implementation_plan: list[str] = field(default_factory=list)
    test_plan: list[str] = field(default_factory=list)
    parent_skill: str | None = None
    expected_improvement: str = ""
    evidence: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "CREATE"

    def to_dict(self):
        return asdict(self)


@dataclass
class SkillEvaluation:
    skill: str
    version: str
    tests_passed: int = 0
    tests_failed: int = 0
    regression_failures: int = 0
    success_rate: float = 0.0
    latency: float = 0.0
    errors: list[str] = field(default_factory=list)
    security_result: str = "NOT_RUN"
    compatibility_result: str = "NOT_RUN"
    recommendation: str = "REJECT"
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self):
        return asdict(self)


class EvolutionStore:
    """Version lineage and lifecycle state; old registry fields remain intact."""

    def __init__(self, path=None):
        self.path = path or os.environ.get("LETHICA_EVOLUTION_FILE") or EVOLUTION_FILE

    def data(self):
        d = _load(self.path, {"version": 1, "skills": {}, "evolutions": []})
        d.setdefault("version", 1); d.setdefault("skills", {}); d.setdefault("evolutions", [])
        return d

    def save(self, data):
        _save(self.path, data)

    def skill(self, name):
        return self.data()["skills"].get(name)

    def versions(self, name):
        return (self.skill(name) or {}).get("versions", [])

    def record(self, name, version_record):
        d = self.data()
        item = d["skills"].setdefault(name, {"name": name, "active_version": None, "versions": []})
        ids = {v.get("version") for v in item["versions"]}
        if version_record.get("version") in ids:
            # Immutable: only a clearly separate evaluation event may be added.
            return False
        item["versions"].append(copy.deepcopy(version_record))
        d["evolutions"].append({"at": _now(), "skill": name,
                                 "version": version_record.get("version"),
                                 "status": version_record.get("status"),
                                 "reason": version_record.get("reason", "")})
        self.save(d)
        return True

    def update_version(self, name, version, **changes):
        d = self.data(); item = d["skills"].get(name)
        if not item: return False
        for rec in item.get("versions", []):
            if rec.get("version") == version:
                # Metadata/status updates are events on the version, not replacement.
                for key, value in changes.items():
                    if key not in ("version", "parent_version", "created_at"):
                        rec[key] = copy.deepcopy(value)
                self.save(d); return True
        return False

    def set_active(self, name, version):
        d = self.data(); item = d["skills"].get(name)
        if not item or not any(v.get("version") == version for v in item.get("versions", [])):
            return False
        item["active_version"] = version
        self.save(d); return True


STORE = EvolutionStore()


def _meta(name):
    return registry.get(name)


def _capabilities(meta):
    if not meta:
        return []
    return [str(x) for x in meta.get("capabilities", [])]


def _skill_health(meta):
    if not meta:
        return None
    try:
        return registry.health(meta.get("name"))
    except Exception:
        return str(meta.get("status", "UNVERIFIED")).upper()


def detect_gaps(task_id, requirements, evidence=None):
    """Capability-based gap detection; exact skill names are not required."""
    out = []
    evidence = list(evidence or [])
    for required in requirements or []:
        rq = _norm(required)
        matches = []
        for name, meta in registry.entries().items():
            hay = {_norm(name), _norm(meta.get("name", "")),
                   *(_norm(x) for x in _capabilities(meta)), _norm(meta.get("description", ""))}
            if rq and any(rq == x or rq in x or x in rq for x in hay if x):
                matches.append((name, meta))
        healthy = [name for name, meta in matches if _skill_health(meta) == "HEALTHY"]
        degraded = [name for name, meta in matches if _skill_health(meta) in ("DEGRADED", "BROKEN", "STALE")]
        if healthy:
            action, severity = "USE_EXISTING", "LOW"
            ev = [{"type": "skill", "id": n, "detail": "healthy capability match"} for n in healthy[:3]]
        elif degraded:
            action, severity = ("REPAIR" if any(_skill_health(m) == "BROKEN" for n, m in matches)
                                else "UPGRADE"), "HIGH"
            ev = [{"type": "skill", "id": n, "detail": "degraded capability match"} for n in degraded[:3]]
        elif matches:
            action, severity = "RESEARCH_MORE", "MEDIUM"
            ev = [{"type": "skill", "id": n, "detail": "unverified capability match"} for n, _ in matches[:3]]
        else:
            action, severity, ev = "CREATE_NEW", "MEDIUM", []
        out.append(SkillGap(task_id, required, [n for n, _ in matches],
                            [] if matches else [required], ev + evidence[:3], severity, action))
    return out


def duplicate_match(proposal: SkillProposal):
    """Return existing skill if capabilities/normalized name already satisfy it."""
    target_caps = {_norm(x) for x in proposal.capabilities}
    target_name = _norm(proposal.name)
    hits = []
    for name, meta in registry.entries().items():
        caps = {_norm(x) for x in _capabilities(meta)}
        if target_caps and target_caps <= caps:
            hits.append((name, "exact capability match"))
        elif target_name and (target_name == _norm(name) or target_name == _norm(name.split("/")[-1])):
            hits.append((name, "normalized name match"))
    return hits


def classify_risk(proposal: SkillProposal):
    # Inspect semantic values, not field names (``security_level`` itself is
    # not evidence of a security-sensitive skill).
    values = [proposal.name, proposal.purpose, *proposal.capabilities,
              *proposal.dependencies, *proposal.tools,
              *proposal.implementation_plan, *proposal.test_plan,
              proposal.expected_improvement, proposal.security_level]
    text = " ".join(map(str, values)).lower()
    if any(x in text for x in ("privileged", "destructive", "credential", "auth", "security")):
        return "CRITICAL"
    if any(x in text for x in ("system", "integration", "mutation")):
        return "HIGH"
    if any(x in text for x in ("network", "api", "filesystem", "write")):
        return "MEDIUM"
    return "LOW"


def dependency_analysis(proposal: SkillProposal):
    available = {name for name in registry.entries()}
    missing = sorted(set(proposal.dependencies) - available)
    dependents = []
    for name, meta in registry.entries().items():
        if set(proposal.dependencies) & set(meta.get("dependencies", [])) or name in proposal.dependencies:
            dependents.append(name)
    return {"available": not missing, "missing": missing, "dependent_skills": sorted(set(dependents)),
            "architecture": "compatible" if not missing else "missing_dependency"}


def create_snapshot(skill, version=None):
    """Snapshot active file and registry before any promotion; never overwrites it."""
    meta = registry.get(skill)
    if not meta:
        return {"ok": False, "error": "skill not found"}
    stamp = hashlib.sha256(f"{skill}:{version or meta.get('version')}:{_now()}".encode()).hexdigest()[:16]
    dest = os.path.join(SNAPSHOT_DIR, stamp)
    os.makedirs(dest, exist_ok=False)
    src = tools._SKILL_INDEX.get(skill) if hasattr(tools, "_SKILL_INDEX") else None
    if not src:
        src = os.path.join(tools.SKILL_DIR, skill, "SKILL.md")
    if os.path.isfile(src):
        shutil.copy2(src, os.path.join(dest, "SKILL.md"))
    _save(os.path.join(dest, "registry.json"), registry._load_raw())
    snap = {"id": stamp, "skill": skill, "version": version,
            "path": dest, "created_at": _now()}
    _save(os.path.join(dest, "snapshot.json"), snap)
    return {"ok": True, **snap}


def _candidate_dir(skill, version):
    path = os.path.join(CANDIDATE_DIR, _norm(skill), version)
    os.makedirs(path, exist_ok=True)
    return path


def propose(proposal: SkillProposal, task_id="", research=None):
    proposal.security_level = proposal.security_level or classify_risk(proposal)
    proposal.evidence.extend(research or [])
    dup = duplicate_match(proposal)
    # v3.6: konsultasi Knowledge Graph sebelum mengubah skill (Phase 30) — impact analysis.
    impact = None
    try:
        from core import capture as graph_capture, graph as G
        node = G.find_by_name(proposal.name, type="SKILL")
        if node:
            impact = graph_capture.impact_analysis(node["id"], max_depth=2, max_nodes=50)
        elif proposal.mode in ("IMPROVE", "REPAIR", "ADAPT", "MIGRATE"):
            impact = {"warning": "canonical skill node belum ada di graph",
                      "mode": proposal.mode}
    except Exception:
        impact = None
    if dup and proposal.mode == "CREATE":
        return {"ok": False, "action": "USE_EXISTING", "duplicates": dup,
                "proposal": proposal.to_dict(), "graph_impact": impact}
    deps = dependency_analysis(proposal)
    if not deps["available"]:
        return {"ok": False, "action": "REJECT", "reason": "missing dependencies",
                "dependencies": deps, "graph_impact": impact}
    # v3.4/Phase 43: IMPROVE/REPAIR/ADAPT/MIGRATE WAJIB resolve ke skill kanonik yang ada
    if proposal.mode in ("IMPROVE", "REPAIR", "ADAPT", "MIGRATE"):
        canonical = registry.get(proposal.name) or (dup[0] if dup else None)
        if not canonical:
            return {"ok": False, "action": "REJECT",
                    "reason": f"{proposal.mode} requires existing canonical skill "
                              f"'{proposal.name}' — CREATE is a separate mode",
                    "graph_impact": impact}
    return {"ok": True, "proposal": proposal.to_dict(), "duplicates": dup,
            "dependencies": deps, "risk": classify_risk(proposal),
            "graph_impact": impact}


def build_candidate(proposal: SkillProposal, content: str, task_id="", reason=""):
    budget = EvolutionBudget.load()
    if not budget.enabled:
        return {"ok": False, "action": "ABORT", "reason": "skill evolution disabled"}
    check = propose(proposal, task_id)
    if not check.get("ok"):
        return check
    # Improvements/repairs follow the canonical existing registry key. This
    # prevents a generated basename from creating a parallel lineage.
    if proposal.mode != "CREATE" and check.get("duplicates"):
        proposal.name = check["duplicates"][0][0]
    if task_id and len([x for x in STORE.data().get("evolutions", [])
                        if x.get("skill") == proposal.name and x.get("task_id") == task_id]) >= budget.max_candidates_per_task:
        return {"ok": False, "action": "ABORT", "reason": "evolution budget exhausted"}
    old = STORE.skill(proposal.name)
    previous = [x.get("version") for x in (old or {}).get("versions", [])]
    parent = (old or {}).get("active_version") or (max(previous, key=_version_parts) if previous else None)
    version = next_version(previous, proposal.mode)
    path = _candidate_dir(proposal.name, version)
    body = content if content.lstrip().startswith("#") else f"# {proposal.name}\n\n## Purpose\n{proposal.purpose}\n\n{content}"
    with open(os.path.join(path, "SKILL.md"), "w", encoding="utf-8") as fh:
        fh.write(body)
    record = {"version": version, "parent_version": parent, "created_at": _now(),
              "description": proposal.purpose, "capabilities": proposal.capabilities,
              "dependencies": proposal.dependencies, "tools": proposal.tools,
              "implementation": path, "tests": proposal.test_plan,
              "status": "DRAFT", "confidence": 0.0, "success_rate": 0.0,
              "failure_rate": 0.0, "usage_count": 0, "repair_count": 0,
              "last_verified": None, "evidence": proposal.evidence,
              "reason": reason, "mode": proposal.mode, "risk": classify_risk(proposal),
              "task_id": task_id, "changes": proposal.implementation_plan}
    if not STORE.record(proposal.name, record):
        return {"ok": False, "action": "REJECT", "reason": "immutable version collision"}
    return {"ok": True, "skill": proposal.name, "version": version,
            "parent_version": parent, "path": path, "status": "DRAFT",
            "proposal": proposal.to_dict()}


def _run_test(command):
    started = time.time()
    result = tools.tool_run_command(command, timeout=120)
    return "[exit=0]" in result, result[:1000], time.time() - started


def evaluate_candidate(skill, version, tests, baseline=None, security_result="PASS",
                       compatibility_result="PASS"):
    rec = next((x for x in STORE.versions(skill) if x.get("version") == version), None)
    if not rec:
        return {"ok": False, "error": "candidate not found"}
    STORE.update_version(skill, version, status="TESTING")
    passed = failed = 0; errors = []; latency = 0.0; evidence = []
    for command in tests or rec.get("tests", []):
        ok, output, elapsed = _run_test(command)
        latency += elapsed
        evidence.append({"type": "test", "command": command, "passed": ok, "output": output[-300:]})
        if ok: passed += 1
        else: failed += 1; errors.append(output[-300:])
    total = passed + failed
    rate = round(passed / total, 3) if total else 0.0
    regression = int((baseline or {}).get("success_rate", rate) > rate) if baseline else 0
    risk = rec.get("risk", "MEDIUM")
    security = security_result if risk != "CRITICAL" else ("PASS" if security_result == "PASS" else "FAIL")
    compatibility = compatibility_result
    recommendation = "PROMOTE" if total and not failed and not regression and security == "PASS" and compatibility == "PASS" else "REJECT"
    evaluation = SkillEvaluation(skill, version, passed, failed, regression, rate, round(latency, 4),
                                 errors, security, compatibility, recommendation, evidence)
    status = "VERIFIED" if recommendation == "PROMOTE" else "REJECTED"
    STORE.update_version(skill, version, status=status, confidence=rate,
                         success_rate=rate, failure_rate=round(failed / total, 3) if total else 1.0,
                         last_verified=_now() if recommendation == "PROMOTE" else None,
                         evaluation=evaluation.to_dict(), evidence=rec.get("evidence", []) + evidence)
    return {"ok": True, **evaluation.to_dict()}


def run_canary(skill, version, runner: Callable | None = None):
    budget = EvolutionBudget.load(); max_tasks = budget.max_canary_tasks
    if max_tasks <= 0:
        return {"ok": False, "recommendation": "REJECT", "reason": "canary budget exhausted"}
    rec = next((x for x in STORE.versions(skill) if x.get("version") == version), None)
    if not rec or rec.get("status") != "VERIFIED":
        return {"ok": False, "recommendation": "REJECT", "reason": "candidate not VERIFIED"}
    failures = 0; results = []
    for i in range(max_tasks):
        try:
            result = bool(runner(skill, version, i)) if runner else True
        except Exception as exc:
            result = False; results.append({"index": i, "error": str(exc)[:200]})
        else:
            results.append({"index": i, "ok": result})
        failures += int(not result)
        if failures > budget.max_canary_failures:
            break
    ok = failures <= budget.max_canary_failures
    STORE.update_version(skill, version, status="VERIFIED" if ok else "REJECTED",
                         canary={"tasks": len(results), "failures": failures, "results": results})
    return {"ok": ok, "recommendation": "PROMOTE" if ok else "ROLLBACK",
            "tasks": len(results), "failures": failures, "results": results}


def promote(skill, version, snapshot=None, canary=None):
    rec = next((x for x in STORE.versions(skill) if x.get("version") == version), None)
    if not rec or rec.get("status") != "VERIFIED":
        return {"ok": False, "action": "REJECT", "reason": "candidate is not VERIFIED"}
    if canary is not None and not canary.get("ok"):
        return rollback(skill, version, snapshot, reason="canary failure")
    src = os.path.join(rec.get("implementation", ""), "SKILL.md")
    if not os.path.isfile(src):
        return {"ok": False, "action": "REJECT", "reason": "candidate implementation missing"}
    dest = os.path.join(tools.SKILL_DIR, skill, "SKILL.md")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    shutil.copy2(src, dest)
    registry.ensure_seeded()
    STORE.update_version(skill, version, status="ACTIVE", promoted_at=_now())
    STORE.set_active(skill, version)
    # Registry metadata is extended, never replaced.
    meta = registry.get(skill)
    if not meta:
        raw = registry._load_raw()
        meta = registry._new_meta(skill, rec.get("description", ""),
                                  capabilities=rec.get("capabilities", []))
        meta["versions"] = []
        raw["skills"][skill] = meta
        registry._save_raw(raw)
        meta = registry.get(skill)
    if meta:
        versions = list(meta.get("versions", []))
        if version not in versions: versions.append(version)
        registry.update(skill, versions=versions, active_version=version,
                       status="verified", last_verified=_now())
    return {"ok": True, "action": "PROMOTE", "skill": skill, "version": version}


def rollback(skill, version, snapshot, reason=""):
    """Restore exact snapshot, then retain failed candidate as REJECTED."""
    if not snapshot or not snapshot.get("path"):
        return {"ok": False, "action": "ROLLBACK", "reason": "snapshot required"}
    snap_dir = snapshot["path"]
    snap_skill = os.path.join(snap_dir, "SKILL.md")
    dest = os.path.join(tools.SKILL_DIR, skill, "SKILL.md")
    if os.path.isfile(snap_skill):
        os.makedirs(os.path.dirname(dest), exist_ok=True); shutil.copy2(snap_skill, dest)
    raw = _load(os.path.join(snap_dir, "registry.json"), None)
    if isinstance(raw, dict):
        registry._save_raw(raw)
    STORE.update_version(skill, version, status="REJECTED", rollback_reason=reason,
                         rollback_at=_now())
    active = STORE.skill(skill)
    if active and active.get("active_version"):
        STORE.set_active(skill, active["active_version"])
    return {"ok": True, "action": "ROLLBACK", "skill": skill, "version": version,
            "reason": reason, "restored_snapshot": snapshot.get("id")}


def evolve(task_id, proposal, content, tests, research=None, baseline=None,
           runner=None, reason=""):
    """Bounded complete lifecycle: propose → build → test → canary → promote."""
    proposal = proposal if isinstance(proposal, SkillProposal) else SkillProposal(**proposal)
    check = propose(proposal, task_id, research)
    if not check.get("ok"):
        record_experience({"task_id": task_id, "skill": proposal.name,
                           "trigger": reason, "proposal": proposal.to_dict(),
                           "result": check.get("action", "REJECT"),
                           "promotion": False, "failure": check})
        return check
    snapshot = create_snapshot(proposal.name) if registry.get(proposal.name) else None
    built = build_candidate(proposal, content, task_id, reason)
    if not built.get("ok"):
        record_experience({"task_id": task_id, "skill": proposal.name,
                           "trigger": reason, "result": "ABORT",
                           "promotion": False, "failure": built})
        return built
    evaluated = evaluate_candidate(proposal.name, built["version"], tests, baseline)
    if not evaluated.get("ok") or evaluated.get("recommendation") != "PROMOTE":
        if built.get("version"): STORE.update_version(proposal.name, built["version"], status="REJECTED")
        result = {"ok": False, "action": "REJECT", "build": built, "evaluation": evaluated}
        record_experience({"task_id": task_id, "skill": proposal.name,
                           "old_version": built.get("parent_version"),
                           "candidate_version": built.get("version"),
                           "trigger": reason, "evaluation": evaluated,
                           "result": "REJECTED", "promotion": False, "failure": result})
        return result
    canary = run_canary(proposal.name, built["version"], runner)
    if not canary.get("ok"):
        rolled = rollback(proposal.name, built["version"], snapshot, "canary failure") if snapshot else canary
        result = {"ok": False, "action": "ROLLBACK" if snapshot else "REJECT",
                  "build": built, "evaluation": evaluated, "canary": canary, "rollback": rolled}
        record_experience({"task_id": task_id, "skill": proposal.name,
                           "old_version": built.get("parent_version"),
                           "candidate_version": built.get("version"),
                           "trigger": reason, "evaluation": evaluated,
                           "result": "ROLLED_BACK", "promotion": False,
                           "rollback": rolled, "failure": canary})
        return result
    promoted = promote(proposal.name, built["version"], snapshot, canary)
    result = {"ok": promoted.get("ok", False), "action": promoted.get("action"),
            "build": built, "evaluation": evaluated, "canary": canary,
            "promotion": promoted, "snapshot": snapshot}
    record_experience({"task_id": task_id, "skill": proposal.name,
                       "old_version": built.get("parent_version"),
                       "candidate_version": built.get("version"), "trigger": reason,
                       "evaluation": evaluated, "result": "PROMOTED" if result["ok"] else "FAILED",
                       "promotion": result["ok"], "rollback": False})
    return result


def record_experience(record):
    """Durable evolution memory, separate file to preserve v3.0-v3.3 records."""
    path = os.path.join(config.LETHICA_DIR, "skill-evolution-history.json")
    data = _load(path, [])
    data.append({**copy.deepcopy(record), "recorded_at": _now()})
    _save(path, data[-300:])
    # v3.5: sink ke semantic long-term memory (Phase 27) — FAILURE/SOLUTION terstruktur.
    # TANPA mengubah behaviour existing; gagal silently diabaikan.
    try:
        from core import memory as semantic_mem
        skill = record.get("skill")
        result = record.get("result")
        failure = record.get("failure") or {}
        if result in ("REJECTED", "ROLLED_BACK", "ABORT", "FAILED"):
            semantic_mem.store(semantic_mem.make_memory(
                "FAILURE", f"skill {skill} evolution {result}",
                f"Skill '{skill}' evolution {result}. Reason: {str(failure)[:300]}",
                tags=["skill", "evolution", str(skill)], skill_id=str(skill),
                source="EXECUTION_EVIDENCE", scope="SKILL", importance=0.7,
                metadata={"version": record.get("candidate_version")}))
        elif result == "PROMOTED":
            semantic_mem.store(semantic_mem.make_memory(
                "SOLUTION", f"skill {skill} evolved ok",
                f"Skill '{skill}' successfully evolved to {record.get('candidate_version')}.",
                tags=["skill", "evolution", str(skill)], skill_id=str(skill),
                source="EXECUTION_EVIDENCE", scope="SKILL", importance=0.7,
                metadata={"version": record.get("candidate_version"), "evidence": "promoted"}))
    except Exception:
        pass
    # v3.6: sink SKILL/SKILL_VERSION ke Knowledge Graph (Phase 18/30).
    # Historical version TIDAK dihapus: versi lama ditandai HISTORICAL + edge SUPERSEDES.
    try:
        from core import capture as graph_capture
        skill = record.get("skill")
        ver = record.get("candidate_version")
        result = record.get("result")
        if skill and ver:
            graph_capture.link_skill_version(
                str(skill), str(ver), parent_version=record.get("old_version"),
                status="ACTIVE" if result == "PROMOTED" else "REJECTED",
                evidence=[f"evolution result={result}",
                          str(record.get("trigger") or "")[:150]])
    except Exception:
        pass
    return data[-1]


def classify_failure(strategy_failed=False, skill_failed=False, environment_failed=False):
    if environment_failed: return "ENVIRONMENT_FAILURE"
    if skill_failed and not strategy_failed: return "SKILL_FAILURE"
    if strategy_failed and not skill_failed: return "STRATEGY_FAILURE"
    if skill_failed and strategy_failed: return "AMBIGUOUS_NEEDS_DIAGNOSIS"
    return "UNKNOWN"
