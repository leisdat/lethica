# core/stats.py — tool usage stats (in-memory, v2.8)
import time

TOOL_STATS = {}  # name -> {"calls": int, "errors": int, "time": float}


def record(name, dt, error=False):
    s = TOOL_STATS.setdefault(name, {"calls": 0, "errors": 0, "time": 0.0})
    s["calls"] += 1
    if error:
        s["errors"] += 1
    s["time"] += dt


def wrap(name, fn):
    """Decorator factory: bungkus tool fn biar tercatat di TOOL_STATS."""
    def wrapper(*a, **kw):
        t0 = time.time()
        try:
            out = fn(*a, **kw)
            err = isinstance(out, str) and out.startswith("Error")
            record(name, time.time() - t0, error=err)
            return out
        except Exception:
            record(name, time.time() - t0, error=True)
            raise
    return wrapper


def summary_text():
    if not TOOL_STATS:
        return "No tool calls yet sesi ini."
    lines = [f"{'tool':<16}{'calls':>6}{'errors':>8}{'total_s':>9}{'avg_ms':>9}", "-" * 48]
    for name, s in sorted(TOOL_STATS.items(), key=lambda x: -x[1]["calls"]):
        avg = (s["time"] / s["calls"] * 1000) if s["calls"] else 0
        lines.append(f"{name:<16}{s['calls']:>6}{s['errors']:>8}{s['time']:>9.1f}{avg:>9.0f}")
    return "\n".join(lines)
