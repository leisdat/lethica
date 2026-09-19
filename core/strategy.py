"""v3.3 Adaptive Planning Engine.

Strategies are planning data, not extra agents.  This module owns the durable
strategy model, bounded candidate generation/selection, and outcome learning.
It deliberately has no LLM or executor dependency so it remains deterministic
and safe to test in isolation.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable

from core import config

STATUSES = ("UNVERIFIED", "HEALTHY", "DEGRADED", "BROKEN", "STALE", "INACTIVE")
STYLES = ("sequential", "parallel", "research_first", "execute_first", "test_first",
          "iterative", "fallback", "conservative", "exploratory")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _cfg() -> dict:
    raw = config.CFG.get("adaptive_planning", {})
    return {
        "enabled": bool(raw.get("enabled", True)),
        "max_candidates": max(1, min(4, int(raw.get("max_candidates", 4)))),
        "exploration_enabled": bool(raw.get("exploration_enabled", True)),
        "exploration_budget": max(0.0, min(1.0, float(raw.get("exploration_budget", 0.15)))),
        "min_evidence_samples": max(1, int(raw.get("min_evidence_samples", 3))),
        "max_strategy_switches": max(0, int(raw.get("max_strategy_switches", 2))),
    }


def _load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


def _save(path: str, value: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(value, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, path)


@dataclass
class Strategy:
    id: str
    name: str
    description: str = ""
    task_patterns: list[str] = field(default_factory=list)
    required_skills: list[str] = field(default_factory=list)
    optional_skills: list[str] = field(default_factory=list)
    required_tools: list[str] = field(default_factory=list)
    execution_style: str = "sequential"
    dependencies: list[str] = field(default_factory=list)
    estimated_cost: float = 1.0
    estimated_duration: float = 1.0
    risk_level: str = "LOW"
    complexity: str = "SIMPLE"
    historical_success: float = 0.0
    recent_success: float = 0.0
    failure_rate: float = 0.0
    sample_count: int = 0
    last_used: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    status: str = "UNVERIFIED"
    success_count: int = 0
    failure_count: int = 0
    repair_count: int = 0
    total_duration: float = 0.0
    total_cost: float = 0.0
    usage_count: int = 0
    failure_streak: int = 0
    recent_outcomes: list[bool] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Strategy":
        fields = cls.__dataclass_fields__
        return cls(**{k: raw[k] for k in fields if k in raw})


class StrategyRegistry:
    """Persistent registry. Historical entries are retained; status is derived."""

    def __init__(self, path: str | None = None):
        self.path = path or os.environ.get("LETHICA_STRATEGY_REGISTRY") or os.path.join(config.LETHICA_DIR, "strategy-registry.json")

    def _data(self) -> dict:
        d = _load(self.path)
        d.setdefault("version", 1)
        d.setdefault("updated", None)
        d.setdefault("strategies", {})
        return d

    def entries(self) -> dict[str, dict]:
        return self._data()["strategies"]

    def get(self, strategy_id: str) -> Strategy | None:
        raw = self.entries().get(strategy_id)
        return Strategy.from_dict(raw) if raw else None

    def register(self, strategy: Strategy | dict) -> Strategy:
        obj = strategy if isinstance(strategy, Strategy) else Strategy.from_dict(strategy)
        data = self._data()
        old = data["strategies"].get(obj.id)
        if old:
            # Candidate metadata may evolve, but counters/evidence never reset.
            for key in ("name", "description", "task_patterns", "required_skills",
                        "optional_skills", "required_tools", "execution_style",
                        "dependencies", "estimated_cost", "estimated_duration",
                        "risk_level", "complexity"):
                data["strategies"][obj.id][key] = getattr(obj, key)
            obj = Strategy.from_dict(data["strategies"][obj.id])
        else:
            data["strategies"][obj.id] = obj.to_dict()
        data["updated"] = _now()
        _save(self.path, data)
        return obj

    def _persist(self, obj: Strategy) -> Strategy:
        """Write a fully-mutated object without treating it as new metadata."""
        data = self._data()
        data["strategies"][obj.id] = obj.to_dict()
        data["updated"] = _now()
        _save(self.path, data)
        return obj

    def update(self, strategy_id: str, **changes) -> Strategy | None:
        obj = self.get(strategy_id)
        if not obj:
            return None
        for key, value in changes.items():
            if key in obj.__dataclass_fields__:
                setattr(obj, key, value)
        return self._persist(obj)

    def search(self, query: str = "") -> list[Strategy]:
        q = set(re.findall(r"[a-z0-9_]+", (query or "").lower()))
        out = []
        for raw in self.entries().values():
            obj = Strategy.from_dict(raw)
            hay = set(re.findall(r"[a-z0-9_]+", json.dumps(raw).lower()))
            if not q or q & hay:
                out.append(obj)
        return sorted(out, key=lambda x: (-x.sample_count, x.id))

    def record_usage(self, strategy_id: str, evidence=None) -> Strategy | None:
        obj = self.get(strategy_id)
        if not obj:
            return None
        obj.usage_count += 1
        obj.last_used = _now()
        if evidence:
            obj.evidence.extend(evidence)
            obj.evidence = obj.evidence[-50:]
        return self._persist(obj)

    def record_outcome(self, strategy_id: str, success: bool, duration=0.0,
                       cost=0.0, repaired=False, evidence=None) -> Strategy | None:
        obj = self.get(strategy_id)
        if not obj:
            return None
        obj.sample_count += 1
        obj.success_count += int(bool(success))
        obj.failure_count += int(not success)
        obj.repair_count += int(bool(repaired))
        obj.total_duration += max(0.0, float(duration or 0))
        obj.total_cost += max(0.0, float(cost or 0))
        obj.failure_streak = 0 if success else obj.failure_streak + 1
        obj.recent_outcomes = (obj.recent_outcomes + [bool(success)])[-10:]
        obj.historical_success = round(obj.success_count / obj.sample_count, 4)
        obj.recent_success = round(sum(obj.recent_outcomes) / len(obj.recent_outcomes), 4)
        obj.failure_rate = round(obj.failure_count / obj.sample_count, 4)
        if evidence:
            obj.evidence.extend(evidence)
            obj.evidence = obj.evidence[-50:]
        obj.status = self._status(obj)
        self._persist(obj)
        # v3.5: sink strategy outcome ke semantic memory (Phase 28) — evidence-based.
        try:
            from core import memory as semantic_mem
            semantic_mem.store(semantic_mem.make_memory(
                "STRATEGY", f"strategy {strategy_id} {'succeeded' if success else 'failed'}",
                f"Strategy '{strategy_id}' outcome: {'success' if success else 'failure'} "
                f"(samples={obj.sample_count}, success_rate={obj.historical_success}).",
                tags=["strategy", str(strategy_id)], strategy_id=str(strategy_id),
                source="EXECUTION_EVIDENCE", scope="STRATEGY", importance=0.6,
                metadata={"success": bool(success), "evidence": evidence}))
        except Exception:
            pass
        # v3.6: sink outcome ke Knowledge Graph (Phase 19) — edge SUCCEEDED_IN / FAILS_WITH.
        try:
            from core import capture as graph_capture
            tasks = [e.get("id") for e in (evidence or []) if e.get("type") == "task_id"]
            if tasks:
                graph_capture.link_strategy_outcome(strategy_id, tasks[-1], bool(success),
                                                    evidence=evidence)
        except Exception:
            pass
        return obj

    def record_repair(self, strategy_id: str, evidence=None) -> Strategy | None:
        obj = self.get(strategy_id)
        if not obj:
            return None
        obj.repair_count += 1
        if evidence:
            obj.evidence.extend(evidence)
            obj.evidence = obj.evidence[-50:]
        return self._persist(obj)

    def record_duration(self, strategy_id: str, duration: float) -> Strategy | None:
        obj = self.get(strategy_id)
        if not obj:
            return None
        obj.total_duration += max(0.0, float(duration or 0))
        return self._persist(obj)

    def record_cost(self, strategy_id: str, cost: float) -> Strategy | None:
        obj = self.get(strategy_id)
        if not obj:
            return None
        obj.total_cost += max(0.0, float(cost or 0))
        return self._persist(obj)

    def mark_degraded(self, strategy_id: str) -> Strategy | None:
        return self.update(strategy_id, status="DEGRADED")

    def mark_inactive(self, strategy_id: str) -> Strategy | None:
        return self.update(strategy_id, status="INACTIVE")

    @staticmethod
    def _status(obj: Strategy) -> str:
        if obj.status == "INACTIVE":
            return "INACTIVE"
        if obj.sample_count >= 3 and obj.failure_streak >= 3:
            return "BROKEN"
        if obj.sample_count >= 3 and obj.recent_success < 0.5:
            return "DEGRADED"
        if obj.sample_count >= 3 and obj.historical_success >= 0.66:
            return "HEALTHY"
        return "UNVERIFIED"


REGISTRY = StrategyRegistry()


def classify_complexity(goal: str) -> str:
    text = (goal or "").strip().lower()
    words = len(text.split())
    if words <= 5 and not re.search(r"research|investigat|debug|analy|compare|multiple|and|dan", text):
        return "TRIVIAL"
    if words <= 16 and not re.search(r"research|investigat|debug|analy|compare|multi|several|dan|lalu", text):
        return "SIMPLE"
    if words <= 35 and not re.search(r"architecture|migration|production|several|multiple|complex", text):
        return "MODERATE"
    if words <= 70:
        return "COMPLEX"
    return "HIGH_COMPLEXITY"


def _strategy(strategy_id: str, name: str, description: str, style: str,
              complexity: str, cost: float, duration: float, risk="LOW",
              patterns=None, required_tools=None) -> Strategy:
    return Strategy(id=strategy_id, name=name, description=description,
                    execution_style=style, complexity=complexity,
                    estimated_cost=cost, estimated_duration=duration,
                    risk_level=risk, task_patterns=patterns or [],
                    required_tools=required_tools or [])


def generate_candidates(goal: str, complexity: str | None = None,
                         max_candidates: int | None = None) -> list[Strategy]:
    """Generate bounded, deterministic candidates; no candidate means no agent."""
    cfg = _cfg()
    level = (complexity or classify_complexity(goal)).upper()
    limit = max_candidates or cfg["max_candidates"]
    limit = max(1, min(4, int(limit)))
    text = (goal or "").lower()
    research = bool(re.search(r"research|investigat|documentation|docs|unknown|cari|riset", text))
    debug = bool(re.search(r"debug|fix|timeout|error|fail|bug|troubleshoot", text))
    candidates = []
    if level == "TRIVIAL":
        candidates = [_strategy("direct", "Direct execution", "Satu aksi langsung tanpa overhead planning.",
                                "execute_first", level, .2, .2, patterns=["trivial"])]
    elif level == "SIMPLE":
        candidates = [_strategy("sequential", "Sequential execution", "Selesaikan langkah inti secara berurutan.",
                                "sequential", level, .5, .5, patterns=["simple"])]
    else:
        candidates = [
            _strategy("execute_first", "Reproduce then execute", "Reproduce/inspect gejala lalu lakukan perubahan dan test.",
                      "execute_first", level, 1.0, 1.0, patterns=["debug", "fix", "timeout"]),
            _strategy("research_first", "Research then execute", "Riset sumber relevan, inspeksi, implementasi, lalu test.",
                      "research_first", level, 1.5, 1.5, patterns=["research", "docs", "unknown"], required_tools=["web_search"]),
            _strategy("inspect_config_first", "Inspect configuration first", "Audit konfigurasi dan lingkungan sebelum reproduksi/perubahan.",
                      "conservative", level, .8, .8, patterns=["config", "environment", "timeout"], risk="LOW"),
            _strategy("test_first", "Test-first diagnosis", "Buat reproduksi/test minimal sebelum implementasi.",
                      "test_first", level, 1.2, 1.1, patterns=["test", "regression"]),
        ]
        if research and not debug:
            candidates = [candidates[1], candidates[2], candidates[0], candidates[3]]
        elif debug:
            candidates = [candidates[0], candidates[2], candidates[1], candidates[3]]
    out = []
    for item in candidates[:limit]:
        out.append(REGISTRY.register(item))
    return out


def _health_penalty(skill_report: dict | None) -> tuple[float, list[str]]:
    report = skill_report or {}
    reasons = []
    if report.get("missing_skills"):
        reasons.append("required skill missing; researcher/builder may be needed")
        return .35, reasons
    if report.get("outdated_skills"):
        reasons.append("outdated skill evidence")
        return .15, reasons
    if report.get("low_confidence"):
        reasons.append("skill evidence low confidence")
        return .08, reasons
    if report.get("available_skills"):
        reasons.append("required skills available")
    return 0.0, reasons


def select_strategy(candidates: Iterable[Strategy], goal: str, memories=None,
                    failures=None, skill_report=None, tried=None,
                    task_id: str = "", available_tools=None) -> dict[str, Any]:
    """Decision support, not blind math. Returns ranked candidates and evidence."""
    cfg = _cfg()
    candidates = list(candidates)
    memories = list(memories or [])
    failures = list(failures or [])
    tried = set(tried or [])
    words = set(re.findall(r"[a-z0-9_]+", (goal or "").lower()))
    skill_penalty, skill_reasons = _health_penalty(skill_report)
    available_tools = set(available_tools or [])
    ranked = []
    for c in candidates:
        fit = .45
        matched = [p for p in c.task_patterns if p in words or p in (goal or "").lower()]
        if matched:
            fit += min(.35, .1 * len(matched))
        if c.id in tried:
            fit -= .7
        rec = REGISTRY.get(c.id) or c
        evidence = []
        reasons = list(skill_reasons)
        if memories:
            evidence.extend({"type": "experience_id", "id": m.get("memory_id"),
                             "detail": "similar task recalled"} for m in memories[:3] if m.get("memory_id"))
            fit += min(.18, .04 * len(memories))
        if failures:
            evidence.extend({"type": "failure_id", "id": f.get("id"),
                             "detail": f.get("root_cause", "known failure")[:120]} for f in failures[:3] if f.get("id"))
            if any(c.id.replace("_first", "") in (f.get("context", "") + f.get("root_cause", "")).lower() for f in failures):
                fit -= .12
        if rec.sample_count >= cfg["min_evidence_samples"]:
            fit += .25 * rec.historical_success + .15 * rec.recent_success
            evidence.append({"type": "strategy_id", "id": c.id, "detail": f"{rec.sample_count} outcome samples"})
        elif rec.sample_count:
            fit += .05 * rec.historical_success
            evidence.append({"type": "strategy_id", "id": c.id, "detail": f"low sample: {rec.sample_count}"})
        else:
            evidence.append({"type": "strategy_id", "id": c.id, "detail": "no historical evidence"})
        if rec.status == "BROKEN":
            fit -= .35
            reasons = ["strategy status BROKEN"]
        elif rec.status == "DEGRADED":
            fit -= .15
            reasons = ["strategy status DEGRADED"]
        prior = [m.get("strategy_id") for m in memories if m.get("strategy_id")]
        if c.id in prior:
            fit += .12
            evidence.append({"type": "experience_id", "id": next(
                (m.get("memory_id") for m in memories if m.get("strategy_id") == c.id), None),
                "detail": "previous task used this strategy"})
            reasons.append("previous similar task used this strategy")
        if c.required_tools and available_tools:
            missing_tools = sorted(set(c.required_tools) - available_tools)
            if missing_tools:
                fit -= .25
                reasons.append("required tools unavailable: " + ", ".join(missing_tools))
        fit -= skill_penalty
        fit -= min(.2, c.estimated_cost * .04)
        fit -= {"LOW": 0, "MEDIUM": .06, "HIGH": .15}.get(c.risk_level, .06)
        if matched:
            reasons.append("task pattern match: " + ", ".join(matched))
        if rec.sample_count < cfg["min_evidence_samples"]:
            reasons.append("evidence_level=LOW (minimum sample threshold not met)")
        else:
            reasons.append("historical and recent success considered")
        ranked.append({"strategy": rec, "score": round(fit, 4), "evidence": evidence,
                       "reasons": reasons, "evidence_level": "HIGH" if rec.sample_count >= cfg["min_evidence_samples"] else "LOW"})
    ranked.sort(key=lambda x: (-x["score"], x["strategy"].id))
    chosen = ranked[0] if ranked else None
    explored = False
    if chosen and cfg["exploration_enabled"] and len(ranked) > 1:
        # Deterministic bounded exploration: stable bucket, observable and reproducible.
        bucket = int(hashlib.sha256((task_id or goal).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
        if bucket < cfg["exploration_budget"]:
            alt = next((x for x in ranked[1:] if x["strategy"].id not in tried), None)
            if alt and alt["score"] >= chosen["score"] - .18:
                chosen, explored = alt, True
                chosen["reasons"].append("bounded exploration budget selected a near-tie")
    if not chosen:
        return {"selected": None, "ranked": [], "explored": False, "confidence": "LOW",
                "reasoning": ["no candidate strategy"], "evidence": []}
    sample = chosen["strategy"].sample_count
    confidence = "HIGH" if sample >= cfg["min_evidence_samples"] and chosen["score"] >= .8 else (
        "MEDIUM" if sample >= cfg["min_evidence_samples"] or chosen["score"] >= .65 else "LOW")
    return {"selected": chosen["strategy"], "ranked": ranked, "explored": explored,
            "confidence": confidence, "reasoning": chosen["reasons"],
            "evidence": chosen["evidence"], "evidence_level": chosen["evidence_level"]}


def classify_failure(task, critic=None) -> dict[str, Any]:
    text = json.dumps({"critic": critic or getattr(task, "critic", {}),
                       "results": getattr(task, "subtask_results", {}),
                       "error": getattr(task, "error", "")}).lower()
    if "permission" in text or "danger" in text or "sandbox" in text:
        kind = "safety_block"
    elif "timeout" in text or "resource_limit" in text:
        kind = "environmental"
    elif "skill" in text and ("missing" in text or "broken" in text):
        kind = "skill_failure"
    elif "depend" in text or "cycle" in text or "dag" in text:
        kind = "dag_error"
    elif "misunderstood" in text or "requirement" in text:
        kind = "task_misunderstood"
    else:
        kind = "execution_failure"
    return {"classification": kind, "text": text[-800:]}


def confidence_for(strategy: Strategy | None, evidence: list | None = None) -> str:
    if not strategy:
        return "LOW"
    n = strategy.sample_count
    if n >= _cfg()["min_evidence_samples"] and strategy.historical_success >= .66:
        return "HIGH"
    if n >= _cfg()["min_evidence_samples"] or (evidence and len(evidence) >= 2):
        return "MEDIUM"
    return "LOW"
