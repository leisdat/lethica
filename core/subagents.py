# core/subagents.py — Sub-agent paralel.
# Agent utama delegasikan subtask independen → N agent mini jalan bareng
# (ThreadPoolExecutor, 1 LClient fresh per thread) → hasil diagregat.
# Sub-agent TIDAK boleh spawn lagi (depth guard) — anti ledakan rekursif.
import concurrent.futures
import threading
import time
import traceback

from core import config, client as client_mod, tags, soul
from core import tooldef as _tooldef

_DEPTH = threading.local()


def in_subagent():
    return getattr(_DEPTH, "n", 0) > 0


def _subagent_system():
    base = soul.build_system_prompt()
    return (base + "\n\n## SUB-AGENT MODE\n"
            "Kamu SUB-AGENT: kerjakan SATU task spesifik yang diberikan, lalu "
            "kembalikan HASIL AKHIR yang ringkas dan lengkap (fakta + file yang "
            "diubah + kesimpulan). DILARANG: panggil tool `spawn`/`subagent` lagi, "
            "ngobrol basa-basi, atau nanya balik — selesaikan langsung.")


def run_one(name, task, model, max_rounds, timeout_s=600):
    """Satu sub-agent: mini agent loop (chat → dispatch tools → loop).
    Return teks hasil (sudah diringkas pemanggil)."""
    _DEPTH.n = getattr(_DEPTH, "n", 0) + 1
    t0 = time.time()
    try:
        cl = client_mod.LClient()  # fresh per thread: state last_tool_calls aman
        model = model or config.DEFAULT_MODEL
        tools_payload = (_tooldef.openai_tools()
                         if getattr(config, "NATIVE_FC", False) else None)
        messages = [
            {"role": "system", "content": _subagent_system()},
            {"role": "user", "content": (
                f"TASK SUB-AGENT '{name}':\n{task}\n\n"
                "Kerjakan sampai selesai dengan tools yang tersedia. "
                "Akhiri dengan ringkasan hasil (maks ~15 baris).")},
        ]
        last_reply, used = "", model
        for rnd in range(max_rounds):
            if time.time() - t0 > timeout_s:
                last_reply += "\n\n[SUB-AGENT TIMEOUT]"
                break
            reply, used = cl.chat_failover(
                model, messages, config.FAILOVER_CHAIN,
                timeout=config.HTTP_TIMEOUT,
                temperature=config.TEMPERATURE, max_tokens=config.MAX_TOKENS,
                tools=tools_payload)
            if reply is None:
                return f"[{name}] ERROR: semua model gagal."
            if getattr(cl, "tools_rejected", False) and tools_payload:
                tools_payload = None
            last_reply = reply or ""
            native_calls = getattr(cl, "last_tool_calls", None)
            if native_calls:
                amsg = {"role": "assistant", "tool_calls": native_calls}
                if last_reply and last_reply != "(empty reply)":
                    amsg["content"] = last_reply
                messages.append(amsg)
                for tc_id, label, out_text in tags.dispatch_calls_list(
                        native_calls, config.SELF_PATH):
                    messages.append({"role": "tool", "tool_call_id": tc_id,
                                     "name": label,
                                     "content": str(out_text)[:8000]})
                continue
            messages.append({"role": "assistant", "content": last_reply})
            out = tags.dispatch(last_reply, config.SELF_PATH)
            if not out:
                break
            messages.append({"role": "user", "content": (
                "Tool results. Lanjut atau finalkan dengan ringkasan hasil.\n\n"
                f"<tool_response>\n{out[:8000]}\n</tool_response>")})
        return f"[{name}] ({used}, {time.time()-t0:.0f}s)\n" + tags.strip_tags(last_reply).strip()
    except Exception as ex:
        return f"[{name}] ERROR: {ex}\n{traceback.format_exc(limit=3)}"
    finally:
        _DEPTH.n = getattr(_DEPTH, "n", 0) - 1


def spawn(tasks, model=None, max_rounds=None, max_workers=None, timeout_s=600):
    """tasks: list dict {"name","task"}. Return string agregat untuk agent utama."""
    max_rounds = max_rounds or getattr(config, "SUBAGENT_MAX_ROUNDS", 4)
    max_workers = max_workers or getattr(config, "SUBAGENT_MAX_WORKERS", 4)
    model = model or config.DEFAULT_MODEL
    if not tasks:
        return "[spawn] ERROR: daftar task kosong."
    if len(tasks) > 8:
        return "[spawn] ERROR: maks 8 sub-agent per panggilan."
    results = [""] * len(tasks)
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(max_workers, len(tasks)),
            thread_name_prefix="subagent") as ex:
        futs = {ex.submit(run_one, t.get("name", f"agent-{i}"),
                           t.get("task", ""), model, max_rounds, timeout_s): i
                for i, t in enumerate(tasks)}
        for fut in concurrent.futures.as_completed(futs, timeout=timeout_s + 60):
            i = futs[fut]
            try:
                results[i] = fut.result(timeout=30)
            except Exception as ex:
                results[i] = f"[{tasks[i].get('name', i)}] ERROR: {ex}"
    combined = "\n\n".join(results)
    return ("HASIL SUB-AGENT PARALEL (gabungkan jadi jawaban final, sebutkan "
            "sumber tiap temuan):\n\n" + combined[:20000])
