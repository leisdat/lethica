# core/orch_state.py — v3.7.2 Orchestrator state primitives (split dari orchestra.py).
# Task terstruktur + logging + limit baca dari config. Tidak import modul orchestrator
# lain (cegah circular). Importer eksternal: `from core.orchestra import Task` (facade).
import os
import re
import json
import time
import threading

from core import config

SUB_STATES = ["PENDING", "READY", "RUNNING", "COMPLETED", "FAILED", "BLOCKED", "CANCELLED"]

# ── task states (ekslisit, terstruktur) ─────────────────────────────
STATES = ["RECEIVED", "PLANNING", "SKILL_ANALYSIS", "RESEARCHING", "EXECUTING",
          "VERIFYING", "DEBUGGING", "REPAIRING", "COMPLETED", "FAILED"]

LOG_FILE = os.path.join(config.LOG_DIR, "orchestra.log")
HIST_FILE = os.path.join(config.LETHICA_DIR, "task-history.json")


def _log(tag, msg, task_id=None):
    tid = f" task={task_id}" if task_id else ""
    line = f"[{time.strftime('%H:%M:%S')}]{tid} [{tag}] {msg}"
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        from core.ui import console
        console.print(f"[dim]{line}[/dim]")
    except Exception:
        print(line)


def _limits():
    g = config.CFG.get("orchestra", {})
    g.setdefault("sub_agent_max_tokens", 1500)
    return {
        "max_agent_steps": int(g.get("max_agent_steps", 12)),
        "max_retries": int(g.get("max_retries", 2)),
        "max_repair_attempts": int(g.get("max_repair_attempts", 2)),
        "timeout": int(g.get("timeout", 1800)),
        "max_tool_calls": int(g.get("max_tool_calls", 40)),
        # v3.2 concurrency budget (default konservatif)
        "max_concurrent_agents": max(1, int(g.get("max_concurrent_agents", 3))),
        "max_total_agent_calls": int(g.get("max_total_agent_calls", 60)),
        "max_subtasks": int(g.get("max_subtasks", 5)),
    }


class Task:
    """State terstruktur satu task. Bukan natural-language."""

    def __init__(self, goal, client=None, model=None):
        self.id = time.strftime("%Y%m%d-%H%M%S") + "-" + re.sub(r"\W+", "", goal[:20]).lower()
        self.goal = goal
        self.state = "RECEIVED"
        self.complexity = "simple"          # simple | complex (auto)
        self.plan = None                    # output Planner
        self.skill_report = None            # output Skill Analyst
        self.research_notes = []
        self.subtask_results = {}           # id → executor result dict
        self.critic = None                  # output Critic terakhir
        self.debug_log = []                 # output Debugger
        self.repair_count = 0
        self.tool_calls = 0
        from core import soul
        self.messages = [{"role": "system", "content": soul.build_system_prompt()}]
        self.client = client
        self.model = model
        self.limits = _limits()
        self.t0 = time.time()
        self.steps = 0
        self.error = None
        # v3.1 experience-aware
        self.lock = threading.Lock()  # v3.2: state utk worker paralel
        self.cancelled = False        # v3.2: flag bounded cancellation
        self.merged = None            # v3.2: output Result Merger
        self.parallel_stats = {"parallel": False, "max_concurrency": 0,
                               "parallel_tasks": 0, "conflicts": 0, "cancellations": 0}
        self.recalled = []           # hasil recall utk planner
        self.recalled_ids = []
        self.sub_states = {}         # subtask id → SUB_STATES
        self.parent_id = None
        self.final_solution = ""
        self.graph = None
        # v3.4 controlled skill evolution evidence
        self.skill_gaps = []
        self.skill_evolution = []
        # v3.3 adaptive planning (strategy is data, not another agent)
        self.semantic_memories = []      # v3.5: memori semantic ter-rank
        self.semantic_scores = []
        self.graph_context = ""          # v3.6: blok konteks knowledge graph
        self.graph_entities = []
        self.graph_paths = []
        self.world_state = None          # v3.6: snapshot world model project
        self.graph_trace = None          # v3.6: jejak update graph (bukti)
        self.strategy_candidates = []
        self.strategy_selection = None
        self.strategy = None
        self.strategy_confidence = "LOW"
        self.strategy_switches = 0
        self.strategy_history = []
        self.strategy_failure = None
        self.planning_metrics = {"strategy_candidates_generated": 0,
                                 "strategy_selected": 0, "strategy_exploration": 0,
                                 "strategy_selection_latency": 0.0,
                                 "planning_latency": 0.0, "execution_latency": 0.0,
                                 "total_latency": 0.0}

    def transition(self, new_state):
        assert new_state in STATES, f"state tidak dikenal: {new_state}"
        _log("CORE", f"{self.state} → {new_state}", self.id)
        self.state = new_state
        self.steps += 1

    def elapsed(self):
        return time.time() - self.t0

    def to_dict(self):
        return {"id": self.id, "goal": self.goal[:200], "state": self.state,
                "complexity": self.complexity, "steps": self.steps,
                "tool_calls": self.tool_calls, "repairs": self.repair_count,
                "elapsed": round(self.elapsed(), 1),
                "subtasks": len((self.plan or {}).get("subtasks", [])),
                "critic_status": (self.critic or {}).get("status"),
                "memory_used": self.recalled_ids,
                "sub_states": self.sub_states,
                "strategy_id": self.strategy.id if self.strategy else None,
                "strategy_confidence": self.strategy_confidence,
                "strategy_switches": self.strategy_switches,
                "planning_metrics": self.planning_metrics,
                "error": self.error}
