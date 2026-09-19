# core/tokens.py — v2.5 token accounting: log usage per call, daily totals, budget guard
import os
import re
import json
import time
import threading

from core import config

TOK_DIR = os.path.join(config.LOG_DIR, "tokens")
os.makedirs(TOK_DIR, exist_ok=True)
_LOCK = threading.Lock()


def _today_file():
    return os.path.join(TOK_DIR, time.strftime("%Y%m%d") + ".jsonl")


def _state_file():
    return os.path.join(TOK_DIR, "_state.json")


def record(model, usage, meta=None):
    """Append satu entri usage. usage: dict prompt/completion/total (boleh None → estimasi).
    Return (prompt_tokens, completion_tokens, total_tokens) yang terekam."""
    u = usage if isinstance(usage, dict) else {}
    pt = int(u.get("prompt_tokens") or 0)
    ct = int(u.get("completion_tokens") or 0)
    if not pt and not ct and meta:
        # estimasi kasar 4 chars/token dari meta (hemat, tanpa tokenizer)
        pt = int(meta.get("req_chars") or 0) // 4
        ct = int(meta.get("reply_chars") or 0) // 4
    tot = u.get("total_tokens") or (pt + ct)
    rec = {
        "ts": time.strftime("%H:%M:%S"),
        "model": model,
        "pt": pt, "ct": ct, "tot": tot,
    }
    if meta:
        rec["meta"] = {k: v for k, v in meta.items() if v is not None}
    with _LOCK:
        try:
            with open(_today_file(), "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except Exception:
            pass
    return pt, ct, tot


def day_summary(day=None):
    """Aggregate satu hari → dict. day=YYYYMMDD (default hari ini)."""
    path = os.path.join(TOK_DIR, (day or time.strftime("%Y%m%d")) + ".jsonl")
    s = {"pt": 0, "ct": 0, "tot": 0, "calls": 0, "models": {}}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                s["pt"] += r.get("pt", 0)
                s["ct"] += r.get("ct", 0)
                s["tot"] += r.get("tot", 0)
                s["calls"] += 1
                m = r.get("model") or "?"
                ms = s["models"].setdefault(m, {"calls": 0, "tot": 0})
                ms["calls"] += 1
                ms["tot"] += r.get("tot", 0)
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return s


def budget_status():
    """Return (used, budget, pct) — budget dari config [model] daily_budget."""
    s = day_summary()
    budget = config.DAILY_BUDGET
    if not budget:
        return s["tot"], 0, 0.0
    return s["tot"], budget, min(100.0, s["tot"] * 100.0 / budget)


def budget_warning():
    """Return string warning atau None kalau lewat 80% budget."""
    used, budget, pct = budget_status()
    if not budget or pct < 80.0:
        return None
    return f"⚠ token budget: {used}/{budget} ({pct:.0f}%) hari ini"


def budget_ok():
    """Hard guard: Return (ok, message). ok=False kalau budget harian habis (>=100%)."""
    used, budget, pct = budget_status()
    if not budget:
        return True, ""
    if pct >= 100.0:
        return False, f"✖ token budget habis: {used}/{budget} ({pct:.0f}%) hari ini — naikkan [model] daily_budget di config.toml"
    if pct >= 80.0:
        return True, f"⚠ token budget: {used}/{budget} ({pct:.0f}%) hari ini"
    return True, ""


def budget_remaining():
    """Return sisa budget (int) atau None kalau budget off."""
    used, budget, _ = budget_status()
    if not budget:
        return None
    return max(0, budget - used)


def summary_text():
    """Ringkasan multi-hari buat /tokens."""
    lines = []
    try:
        files = sorted(f for f in os.listdir(TOK_DIR) if f.endswith(".jsonl"))
    except Exception:
        files = []
    for fn in files[-7:]:
        day = fn[:-6]
        s = day_summary(day)
        if s["calls"]:
            lines.append(f"  {day}: {s['tot']:>8,} tok | {s['calls']:>4} calls | p{s['pt']:,} c{s['ct']:,}")
    used, budget, pct = budget_status()
    out = ["📊 TOKEN USAGE (7 hari terakhir)"]
    out.extend(lines or ["  (no data)"])
    if budget:
        bar = "█" * int(pct // 5) + "░" * (20 - int(pct // 5))
        out.append(f"\n  Budget: {used:,}/{budget:,} [{bar}] {pct:.0f}%")
    else:
        out.append(f"\n  Today: {used:,} tok (budget off — set [model] daily_budget)")
    return "\n".join(out)
