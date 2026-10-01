#!/usr/bin/env python3
"""tests/run_all.py — runner untuk test suite Lethica skill/loader/sysprompt/e2e.
Jalankan: python3 ~/lethica/tests/run_all.py
"""
import os, sys, subprocess, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
TESTS = [
    "test_skills_loader.py",
    "test_sysprompt.py",
    "test_e2e_spawn.py",
    "test_v30_orchestrator.py",
    "test_v31_experience.py",
    "test_v32_parallel.py",
    "test_v33_adaptive.py",
    "test_v34_evolution.py",
    "test_v37_toolcalling.py",
    "test_v371_memorydb.py",
]
def main():
    total_fail = 0
    strategy_store = os.path.join(tempfile.mkdtemp(prefix="lx-v33-suite-"),
                                  "strategy-registry.json")
    # v3.6.1: isolasi TOTAL — arahkan SEMUA state persisten (memory, graph,
    # experience, sessions) ke workspace temp per-suite. Test v32 seed semantic
    # memory & graph; tanpa redirect mereka bocor ke production lineage
    # (hits 80→90) dan timing membengkak (0.41s→0.60s, gagal threshold 0.45s).
    iso_ws = tempfile.mkdtemp(prefix="lx-suite-isolated-")
    for t in TESTS:
        print("\n" + "="*60)
        print("RUN:", t)
        print("="*60)
        env = os.environ.copy()
        env["LETHICA_STRATEGY_REGISTRY"] = strategy_store
        # v3.6.1: isolasi state PERSISTEN berat (semantic memory + graph) ke temp.
        # Tanpa ini test v32 seed 80-90 memory/graph ke production → timing
        # membengkak 0.41s→0.60s (gagal threshold 0.45s) + lineage tercemar.
        # JANGAN redirect LETHICA_DIR — itu memutus skills/ & workspace (test skill).
        env["LETHICA_MEM_DIR"] = os.path.join(iso_ws, t, "memory")
        env["LETHICA_GRAPH_DIR"] = os.path.join(iso_ws, t, "graph")
        p = subprocess.run([sys.executable, os.path.join(HERE, t)],
                          capture_output=True, text=True, env=env)
        print(p.stdout)
        if p.stderr.strip():
            print("[stderr]", p.stderr[:500])
        if p.returncode != 0:
            total_fail += 1
    print("\n" + "="*60)
    print("RESULT:", "ALL GREEN" if total_fail == 0 else f"{total_fail} suite gagal")
    print("="*60)
    return total_fail
if __name__ == "__main__":
    sys.exit(main())
