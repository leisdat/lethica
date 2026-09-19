import sys
sys.path.insert(0, "/data/data/com.termux/files/home/lethica")
from core import orchestra

goal = (
    "Buat file workspace/hello_live.py berisi kode Python yang print 'hello lethica'. "
    "Jalankan dengan python3 dan verifikasi outputnya. Laporkan status."
)
print("=== LIVE E2E (default=cline) ===", flush=True)
t = orchestra.start(goal, model="cline/z-ai/glm-5.3-flash")
print("\n=== RESULT ===", flush=True)
print("state:", t.state, flush=True)
print("error:", getattr(t, "error", None), flush=True)
print("final_solution:", (getattr(t, "final_solution", "") or "")[:250], flush=True)
print("subtask_results:", {k: v.get("status") for k, v in (getattr(t, "subtask_results", {}) or {}).items()}, flush=True)
print("repair_count:", getattr(t, "repair_count", 0), flush=True)
print("elapsed_s:", round(t.elapsed(), 1), flush=True)