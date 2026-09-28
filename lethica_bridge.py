#!/data/data/com.termux/files/usr/bin/python3
# lethica_bridge.py — Telegram bridge untuk Lethica (v1.2)
# Chat bebas + tools (web_search, browse, memory, plan, rag, file ops, shell exec sandboxed).
# Per-chat conversation memory (persist ke disk), streaming progress tiap tool-round,
# per-chat model switch, auto-reload state on boot.
# Run: python3 ~/lethica/lethica_bridge.py   (long-lived)
#
# Struktur:
#   _load_lethica()      — import lethica.py sebagai library (tanpa TUI main loop)
#   per-chat state       — CHATS dict: system prompt + history + model per chat_id
#   state persistence    — ~/lethica/workspace/chats.json (load/save)
#   _agent_turn          — agent loop sinkron (executor thread) + progress callback
#   handlers             — /start /new /model <nama> /status /help + on_text
#   main                 — polling loop

import asyncio
import functools
import json
import os
import re
import time
import sys
import time

# Lokasi repo: dari file ini sendiri (jangan hardcode ~/lethica — di mesin lain crash).
LETHICA_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LETHICA_DIR)
CHATS_FILE = os.path.join(LETHICA_DIR, "workspace", "chats.json")

# Scrub entri bracket IPv6 di no_proxy yang bikin httpx crash ("Invalid port").
for _var in ("no_proxy", "NO_PROXY"):
    _v = os.environ.get(_var, "")
    os.environ[_var] = ",".join(e for e in _v.split(",") if e and not e.startswith("["))

# ── Lethica sebagai library (jangan jalankan TUI main loop) ─────────

def _load_lethica():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "lethica", os.path.join(LETHICA_DIR, "lethica.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lethica"] = mod
    spec.loader.exec_module(mod)
    return mod


lethica = _load_lethica()

from telegram import Update                                    # noqa: E402
from telegram.constants import ChatAction                      # noqa: E402
from telegram.ext import (Application, CommandHandler,          # noqa: E402
                          MessageHandler, ContextTypes, filters)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "") or (
    open(os.path.expanduser("~/.hermes/agent_bot_token")).read().strip()
    if os.path.isfile(os.path.expanduser("~/.hermes/agent_bot_token")) else "")
MAX_REPLY = 3900          # TG hard cap 4096
MAX_TURNS_STORED = 12     # conversation memory per chat
AUTHORIZED = None         # None = semua chat boleh; atau set {user_id} untuk lock

TOOL_TAG_RE = re.compile(
    r"<(invoke|read_file|write_file|edit_file|list_dir|search_content|"
    r"http_request|download_file|web_search|browse|memory|plan|rag|skill|run_code)\b"
    r".*?(/>|</\1>)", re.DOTALL)

PROGRESS = ["🔧", "🛠", "⚙️", "🔬", "📡", "🧪", "📦", "🚀"]

# ── Per-chat state (persist) ────────────────────────────────────────

CLIENT = lethica.LClient(lethica.DEFAULT_BASE, lethica.API_KEY)
CHATS = {}  # chat_id -> {"messages": [...], "model": str}


def _default_state():
    return {
        "messages": [{"role": "system", "content": lethica.build_system_prompt()}],
        "model": lethica.DEFAULT_MODEL,
        "pending_plan": None,  # plan text menunggu approval (plan mode)
        "pending_goal": None,  # goal asal plan pending (untuk revisi)
    }


def _chat(chat_id):
    if chat_id not in CHATS:
        CHATS[chat_id] = _default_state()
    return CHATS[chat_id]


def _reset(chat_id):
    CHATS[chat_id] = _default_state()


def _save_state():
    """Persist CHATS ke disk (messages di-trim, system prompt gak disimpan)."""
    try:
        payload = {}
        for cid, st in CHATS.items():
            msgs = [m for m in st["messages"] if m.get("role") != "system"]
            payload[str(cid)] = {"model": st["model"], "messages": msgs,
                                 "pending_plan": st.get("pending_plan")}
        with open(CHATS_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
    except Exception:
        pass


def _load_state():
    """Load CHATS dari disk kalau ada (inject system prompt fresh)."""
    global CHATS
    try:
        if not os.path.isfile(CHATS_FILE):
            return
        with open(CHATS_FILE, encoding="utf-8") as f:
            payload = json.load(f)
        sys_prompt = lethica.build_system_prompt()
        for cid, st in payload.items():
            msgs = [{"role": "system", "content": sys_prompt}] + (st.get("messages") or [])
            CHATS[int(cid) if cid.isdigit() else cid] = {
                "messages": msgs,
                "model": st.get("model", lethica.DEFAULT_MODEL),
                "pending_plan": st.get("pending_plan"),
            }
    except Exception:
        pass


def _fmt_tool_results(out, limit=1800):
    """Ringkas tool results buat context TG (hemat token)."""
    return out[:limit] + ("\n... (truncated)" if len(out) > limit else "")


# ── Agent loop ──────────────────────────────────────────────────────

def _run_agent_turn(messages, model, user_text, progress_cb=None, plan_approved=False):
    """Sinkron agent loop. Return (final_text, used, status).
    status: done | plan_pending | failed.
    progress_cb(round_idx, kind, info) untuk status ke TG.
    v3.7: pakai core.tooldef schema (native FC kalau provider dukung, auto-degrade)
    + dispatcher tervalidasi lethica.tags — TOOL_TAG_RE manual dibuang."""
    from core import tooldef as _tooldef
    from core import planmode as _planmode
    messages.append({"role": "user", "content": user_text})
    final_text = None
    used = None
    last_reply = None
    # ── PLAN MODE gate: task terdeteksi → susun plan, STOP, tunggu approval ──
    # v3.8.1: draft_plan return None kalau model gagal total → skip gate,
    # eksekusi langsung (user minta kerja, bukan pesan error).
    if _planmode.should_draft(user_text, plan_approved=plan_approved):
        plan_text, pused = _planmode.draft_plan(user_text, model, CLIENT)
        if plan_text is not None:
            return plan_text, pused, "plan_pending"
    rounds = max(1, int(lethica.MAX_TOOL_ROUNDS))
    tools_payload = _tooldef.openai_tools() if getattr(lethica.config, "NATIVE_FC", False) else None
    for i in range(rounds):
        if progress_cb:
            progress_cb(i, "thinking", None)
        t_call = time.time()
        # v3.8.3: pakai jalur STREAMING (stream_cb) — guard first-data 30 dtk
        # & total 90 dtk per leg berlaku. Jalur non-streaming bisa ngegantung
        # 60 dtk × 3 attempt per model = ratusan detik per round.
        reply, used = CLIENT.chat_failover(
            model, messages, lethica.FAILOVER_CHAIN,
            temperature=lethica.TEMPERATURE, max_tokens=lethica.MAX_TOKENS,
            timeout=lethica.HTTP_TIMEOUT, tools=tools_payload,
            stream_cb=lambda delta, kind: None)
        if reply is None:
            # v3.8.1: transient blip → 1x percobaan ulang sebelum nyerah.
            # v3.8.3: retry HANYA kalau gagal CEPAT (<45 dtk, kemungkinan blip).
            # Kalau sudah bakar puluhan detik (model hang), retry langsung
            # cuma menggandakan penderitaan → nyerah, user bisa coba lagi.
            if time.time() - t_call < 45:
                time.sleep(2)
                reply, used = CLIENT.chat_failover(
                    model, messages, lethica.FAILOVER_CHAIN,
                    temperature=lethica.TEMPERATURE, max_tokens=lethica.MAX_TOKENS,
                    timeout=lethica.HTTP_TIMEOUT, tools=tools_payload,
                    stream_cb=lambda delta, kind: None)
            if reply is None:
                return None, None, "failed"
        if getattr(CLIENT, "tools_rejected", False) and tools_payload:
            tools_payload = None
        reply = lethica.terse_filter(reply)
        last_reply = reply
        # ── jalur native FC ──
        native_calls = getattr(CLIENT, "last_tool_calls", None)
        if native_calls:
            amsg = {"role": "assistant", "tool_calls": native_calls}
            if reply and reply != "(empty reply)":
                amsg["content"] = reply
            messages.append(amsg)
            for tc_id, label, out_text in lethica.tags.dispatch_calls_list(
                    native_calls, lethica.SELF_PATH):
                messages.append({"role": "tool", "tool_call_id": tc_id,
                                 "name": label, "content": _fmt_tool_results(str(out_text), 3000)})
            if progress_cb:
                progress_cb(i, "tool", used)
            continue
        # ── jalur tag legacy (regex + salvage tervalidasi) ──
        messages.append({"role": "assistant", "content": reply})
        out = lethica.dispatch(reply, lethica.SELF_PATH)
        if not out:
            final_text = lethica.strip_tags(reply)
            break
        if progress_cb:
            progress_cb(i, "tool", used)
        messages.append({"role": "user", "content": (
            "Tool results (lethica sandbox). Lanjut atau finalkan.\n\n"
            "<tool_response>\n" + _fmt_tool_results(out) + "\n</tool_response>"
        )})
    else:
        # v2.9.2 fix: dulu ambil messages[-1] (= tool_response mentah, bocor ke chat).
        # Sekarang pakai jawaban assistant terakhir yang beneran.
        final_text = lethica.strip_tags(last_reply or "")
    # trim conversation: keep system + last MAX_TURNS_STORED*2
    if len(messages) > MAX_TURNS_STORED * 2 + 1:
        messages[:] = [messages[0]] + messages[-(MAX_TURNS_STORED * 2):]
    return final_text, used, "done"


async def _agent_turn(chat_id, user_text, progress_cb=None, plan_approved=False):
    """Jalankan agent loop (sinkron, di thread executor) → return (final, used, status)."""
    state = _chat(chat_id)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(_run_agent_turn, state["messages"], state["model"],
                          user_text, progress_cb, plan_approved))


# ── Reply helpers ───────────────────────────────────────────────────

async def _reply_long(update, text):
    """Kirim text, auto-split kalau > MAX_REPLY."""
    if len(text) <= MAX_REPLY:
        await update.message.reply_text(text, parse_mode=None)
        return
    for i in range(0, len(text), MAX_REPLY):
        await update.message.reply_text(text[i:i + MAX_REPLY], parse_mode=None)


async def _edit_or_send(update, msg, text):
    """Edit pesan status kalau bisa, else kirim baru."""
    try:
        await msg.edit_text(text, parse_mode=None)
    except Exception:
        await update.message.reply_text(text, parse_mode=None)


async def _keepalive(ctx, chat_id, status_msg, t0, last_edit=None):
    """v3.8.2: selama turn jalan, jaga indikator 'typing…' tetap hidup
    (Telegram mematikannya tiap ~5 dtk) + update elapsed time tiap ~8 dtk
    biar user lihat agent-nya kerja, bukan mati. Di-cancel setelah turn selesai."""
    _le = last_edit if last_edit is not None else [0.0]
    try:
        tick = 0
        while True:
            await asyncio.sleep(4)
            tick += 1
            try:
                await ctx.bot.send_chat_action(chat_id=chat_id,
                                               action=ChatAction.TYPING)
            except Exception:
                pass
            if tick % 2 == 0 and time.time() - _le[0] > 6:
                _le[0] = time.time()
                try:
                    await status_msg.edit_text(
                        f"🤖 mikir… ({time.time() - t0:.0f} dtk)", parse_mode=None)
                except Exception:
                    pass
    except asyncio.CancelledError:
        pass


# ── Handlers ────────────────────────────────────────────────────────

HELP_TEXT = (
    "🤖 *Lethica* online — agent loop + tools via 9Router\n\n"
    "Kirim chat bebas, aku jalankan agent (web\\_search, browse, memory, plan, rag, file, shell).\n\n"
    "📋 *Plan mode* aktif (auto): task terdeteksi → aku susun rencana dulu, "
    "balas *gas* untuk eksekusi.\n"
    "🚀 *Sub-agent paralel*: task besar otomatis kupecah ke agent mini yang jalan bareng.\n\n"
    "/new — reset percakapan\n/model — info model aktif + failover chain\n"
    "/model &lt;nama&gt; — ganti model chat ini\n/planmode off|auto|always — atur plan mode\n"
    "/status — statistik\n/help — ini")


async def cmd_start(update: Update, ctx):
    await update.message.reply_text(HELP_TEXT, parse_mode="Markdown")


async def cmd_new(update: Update, ctx):
    _reset(update.effective_chat.id)
    _save_state()
    await update.message.reply_text("✓ percakapan di-reset.")


async def cmd_model(update: Update, ctx):
    chat_id = update.effective_chat.id
    state = _chat(chat_id)
    arg = (ctx.args[0] if ctx.args else "") if hasattr(ctx, "args") and ctx.args else ""
    if arg:
        # per-chat model switch
        state["model"] = arg.strip()
        _save_state()
        await update.message.reply_text(f"✓ model chat ini → *{arg}*")
        return
    await update.message.reply_text(
        f"Model: *{state['model']}*\nFailover: {' → '.join(lethica.FAILOVER_CHAIN)}\n"
        f"Persona: {lethica.PERSONA_MODE} | Stream: {lethica.STREAM}")


async def cmd_status(update: Update, ctx):
    state = _chat(update.effective_chat.id)
    n = len(state["messages"]) - 1
    rag = lethica.rag_stats_summary() or "(kosong)"
    mem = (len([f for f in os.listdir(lethica.MEMORY_DIR) if f.endswith(".md")])
           if os.path.isdir(lethica.MEMORY_DIR) else 0)
    await update.message.reply_text(
        f"📊 msgs: {n} | memory files: {mem}\nRAG: {rag}\nbackend: {lethica.DEFAULT_BASE}\nmodel: {state['model']}")


async def cmd_help(update: Update, ctx):
    await cmd_start(update, ctx)


async def cmd_planmode(update: Update, ctx):
    """Toggle plan mode: /planmode off|auto|always"""
    arg = (ctx.args[0] if ctx.args else "").lower() if hasattr(ctx, "args") and ctx.args else ""
    if arg in ("off", "auto", "always"):
        lethica.config.PLAN_MODE = arg
        await update.message.reply_text(f"✓ plan mode → *{arg}*", parse_mode="Markdown")
        return
    await update.message.reply_text(
        f"Plan mode: *{lethica.config.PLAN_MODE}*\n"
        "Pakai: /planmode off|auto|always\n"
        "• off — langsung eksekusi\n• auto — task terdeteksi → plan dulu, tunggu approval\n• always — semua pesan → plan dulu",
        parse_mode="Markdown")


async def _finish_turn(update, status_msg, final, used, t0):
    """Kirim hasil akhir turn ke chat (dipakai alur normal & post-approval)."""
    dt = time.time() - t0
    _save_state()
    if final is None:
        await _edit_or_send(update, status_msg, "✖ semua model gagal. Cek routerku /status.")
        return
    # strip tool tags dari display (jangan bocorin format tag ke chat)
    final = TOOL_TAG_RE.sub("", final).strip() or "(no content)"
    await _edit_or_send(update, status_msg, f"🤖 _{used} · {dt:.0f}s_\n\n{final}")


def _plan_prompt_text(plan_text):
    return (f"📋 *Rencana kerja:*\n\n{plan_text}\n\n"
            "Balas *gas* untuk eksekusi, kirim revisi kalau mau diubah, atau *batal*.")


async def _show_plan(update, status_msg, plan_text):
    """Tampilkan plan pending approval (split kalau kepanjangan)."""
    body = _plan_prompt_text(plan_text)

    async def _send_md(text):
        try:
            await status_msg.edit_text(text, parse_mode="Markdown")
        except Exception:
            await update.message.reply_text(text, parse_mode="Markdown")

    if len(body) <= MAX_REPLY:
        await _send_md(body)
        return
    try:
        await status_msg.edit_text("📋 *Rencana kerja:* (lanjut di bawah)", parse_mode="Markdown")
    except Exception:
        pass
    for i in range(0, len(plan_text), MAX_REPLY):
        await update.message.reply_text(plan_text[i:i + MAX_REPLY], parse_mode=None)
    await update.message.reply_text(
        "Balas *gas* untuk eksekusi, kirim revisi kalau mau diubah, atau *batal*.",
        parse_mode="Markdown")


async def on_text(update: Update, ctx):
    from core import planmode as _planmode
    chat_id = update.effective_chat.id
    if AUTHORIZED is not None and chat_id not in AUTHORIZED:
        await update.message.reply_text("⛔ unauthorized.")
        return
    user_text = (update.message.text or "").strip()
    if not user_text:
        return
    state = _chat(chat_id)

    # ── PLAN MODE: ada plan menunggu approval ──
    if state.get("pending_plan"):
        verdict = _planmode.check_approval(user_text)
        if verdict == "approve":
            plan_text = state["pending_plan"]
            state["pending_plan"] = None
            status_msg = await update.message.reply_text("🚀 plan disetujui, eksekusi…",
                                                         parse_mode=None)
            t0 = time.time()
            ka_task = asyncio.get_running_loop().create_task(
                _keepalive(ctx, chat_id, status_msg, t0))
            try:
                final, used, _st = await _agent_turn(
                    chat_id, _planmode.approval_message(plan_text),
                    None, plan_approved=True)
            except Exception as e:
                ka_task.cancel()
                await _edit_or_send(update, status_msg, f"⚠ agent error: {e}"[:MAX_REPLY])
                return
            ka_task.cancel()
            await _finish_turn(update, status_msg, final, used, t0)
            return
        if verdict == "reject":
            state["pending_plan"] = None
            try:
                lethica.tool_plan("clear")
            except Exception:
                pass
            _save_state()
            await update.message.reply_text("Plan dibatalkan. 👍", parse_mode=None)
            return
        # revise → susun ulang plan dengan feedback user
        status_msg = await update.message.reply_text("📝 revisi plan…", parse_mode=None)
        loop = asyncio.get_running_loop()
        try:
            new_plan, _u = await loop.run_in_executor(
                None, lambda: _planmode.draft_plan(
                    state.get("pending_goal") or user_text, state["model"], CLIENT,
                    context=f"Feedback user untuk revisi: {user_text}"))
        except Exception as e:
            await _edit_or_send(update, status_msg, f"⚠ gagal revisi plan: {e}"[:MAX_REPLY])
            return
        state["pending_plan"] = new_plan
        _save_state()
        await _show_plan(update, status_msg, new_plan)
        return

    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    t0 = time.time()

    # pesan status progress (di-update tiap tool-round)
    status_msg = await update.message.reply_text("🤖 memproses…", parse_mode=None)
    last_edit = [0.0]
    # loop aktif (PTB v22: Application.loop sudah dihapus, ambil dari coroutine ini)
    _loop = asyncio.get_running_loop()

    def _progress(round_idx, kind, used):
        now = time.time()
        if now - last_edit[0] < 1.2:   # throttle edit (maks 1x/1.2s)
            return
        last_edit[0] = now
        icon = PROGRESS[round_idx % len(PROGRESS)]
        if kind == "thinking":
            txt = f"{icon} round {round_idx+1}: mikir…"
        else:
            txt = f"{icon} round {round_idx+1}: jalanin tool ({used})…"
        asyncio.run_coroutine_threadsafe(
            _edit_or_send(update, status_msg, txt), _loop)

    try:
        # v3.8.2: keepalive — typing indicator + elapsed time selama turn jalan
        ka_task = _loop.create_task(_keepalive(ctx, chat_id, status_msg, t0, last_edit))
        try:
            final, used, status = await _agent_turn(chat_id, user_text, _progress)
        finally:
            ka_task.cancel()
    except Exception as e:
        await _edit_or_send(update, status_msg, f"⚠ agent error: {e}"[:MAX_REPLY])
        return
    # ── PLAN MODE: plan butuh approval ──
    if status == "plan_pending":
        state["pending_plan"] = final
        state["pending_goal"] = user_text
        _save_state()
        await _show_plan(update, status_msg, final)
        return
    await _finish_turn(update, status_msg, final, used, t0)


# ── Main ────────────────────────────────────────────────────────────

def _build_app():
    """Bangun PTB Application dengan dukungan proxy env (penting di sandbox/VPS)."""
    if not BOT_TOKEN:
        raise SystemExit(
            "[lethica-bridge] TELEGRAM_BOT_TOKEN kosong.\n"
            "  export TELEGRAM_BOT_TOKEN='isi-token-dari-BotFather' dulu.")
    builder = Application.builder().token(BOT_TOKEN)
    # Timeout longgar: koneksi ke Telegram via proxy sandbox sering lambat/flaky.
    for _m, _v in (("connect_timeout", 30.0), ("read_timeout", 60.0),
                   ("write_timeout", 60.0), ("pool_timeout", 30.0)):
        try:
            builder = getattr(builder, _m)(_v)
        except AttributeError:
            pass
    proxy = (os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
             or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy"))
    if proxy:
        try:
            builder = builder.proxy(proxy).get_updates_proxy(proxy)
            print(f"[lethica-bridge] pakai proxy: {proxy[:30]}...")
        except AttributeError:
            print("[lethica-bridge] builder.proxy() tidak ada; andalkan env proxy httpx.")
    return builder.build()


def _register_handlers(app):
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("planmode", cmd_planmode))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))


def main():
    _load_state()  # restore percakapan lintas restart
    # v3.8.4: self-healing polling loop. Proxy sandbox ke Telegram flaky —
    # NetworkError/ConnectError dulunya MEMBUNUH proses (30x traceback di log),
    # user chat tidak dibalas sampai watchdog eksternal restart (bisa >5 mnt).
    # Sekarang: crash → backoff → rebuild app → polling lagi, di dalam proses.
    backoff = 10
    while True:
        app = _build_app()
        _register_handlers(app)
        print("[lethica-bridge] starting @QMybotai_bot ...")
        try:
            # bootstrap_retries: jangan langsung abort kalau proxy lagi flaky saat start.
            app.run_polling(drop_pending_updates=True, allowed_updates=["message"],
                            bootstrap_retries=10)
            print("[lethica-bridge] polling berhenti normal — keluar.")
            break
        except Exception as e:
            # v3.8.4b: Conflict = ada instance lain yang polling (double-start).
            # Retry TIDAK PERNAH membantu di kasus ini — malah bikin dua
            # instance gelut selamanya. Keluar, biar watchdog yang bereskan.
            if "Conflict" in type(e).__name__ or "terminated by other getUpdates" in str(e):
                print(f"[lethica-bridge] Conflict: instance lain sedang polling — keluar.")
                break
            print(f"[lethica-bridge] polling crash ({type(e).__name__}: {str(e)[:120]}) "
                  f"— coba lagi dalam {backoff} dtk")
            time.sleep(backoff)
            backoff = min(backoff * 2, 300)


if __name__ == "__main__":
    main()
