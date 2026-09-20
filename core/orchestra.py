# core/orchestra.py — v3.7.2 facade (split dari monolit 1577 baris).
# Modul ini TIDAK lagi berisi logika. Ia re-export API publik agar semua importer
# lama (`from core import orchestra`, `orchestra.tags`, `orchestra.tools`, dll)
# tetap berjalan tanpa perubahan.
#
# Krusial: `executor` dan `_run_tools` di-override oleh test
# (`orchestra.executor = fn`). Agar override terlihat oleh scheduler/agents,
# keduanya dijadikan property yang delegate ke `core.orch_agents`.
import sys
import types

from core.orch_state import (  # noqa: F401
    Task, STATES, SUB_STATES, _log, _limits, LOG_FILE, HIST_FILE,
)
from core.orch_agents import (  # noqa: F401
    planner, skill_analyst, critic, debugger, repair,
    _run_tools_in, researcher, build_missing_skills, adaptive_strategy,
    _ask_json, run_subtask, _skill_index_snippet, _scan_cmd_files,
)
from core.orch_scheduler import (  # noqa: F401
    graph_validate, classify_subtask, Scheduler, _execute_serial, _execute_parallel,
    merge_results, redecompose_independent, _deps, _unblock_ready,
    _ready_simple, _worker_fn, _Worker, safe_parallel, predict_writes,
    match_capability,
)
from core.orch_run import (  # noqa: F401
    run, _learn, _history, start, cli_report, report_text, _switch_strategy,
)

# Agar `orchestra.tags` dan `orchestra.tools` tetap jadi module yang diakses
# test (mis. orchestra.tags.dispatch, orchestra.tools.tool_web_search).
import core.tags as tags   # noqa: E402,F401
import core.tools as tools  # noqa: E402,F401


class _OrchestraModule(types.ModuleType):
    """Module-kelas: property executor/_run_tools delegate ke orch_agents."""
    @property
    def executor(self):
        from core import orch_agents
        return orch_agents.executor

    @executor.setter
    def executor(self, fn):
        from core import orch_agents
        orch_agents.executor = fn

    @property
    def _run_tools(self):
        from core import orch_agents
        return orch_agents._run_tools

    @_run_tools.setter
    def _run_tools(self, fn):
        from core import orch_agents
        orch_agents._run_tools = fn


sys.modules[__name__].__class__ = _OrchestraModule
