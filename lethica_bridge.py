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
import sys
import time

LETHICA_DIR = os.path.expanduser("~/lethica")
sys.path.insert(0, LETHICA_DIR)
CHATS_FILE = os.path.join(LETHICA_DIR, "workspace", "chats.json")

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

BOT_TOKEN = open(os.path.expanduser("~/.hermes/agent_bot_token")).read().strip()
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
            payload[str(cid)] = {"model": st["model"], "messages": msgs}
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
            }
    except Exception:
        pass


def _fmt_tool_results(out, limit=1800):
    """Ringkas tool results buat context TG (hemat token)."""
    return out[:limit] + ("\n... (truncated)" if len(out) > limit else "")


# ── Agent loop ──────────────────────────────────────────────────────

def _run_agent_turn(messages, model, user_text, progress_cb=None):
    """Sinkron agent loop. Return (final_text, used) atau (None, None).
    progress_cb(round_idx, kind, info) untuk status ke TG."""
    messages.append({"role": "user", "content": user_text})
    final_text = None
    used = None
    last_reply = None
    rounds = max(1, int(lethica.MAX_TOOL_ROUNDS))
    for i in range(rounds):
        if progress_cb:
            progress_cb(i, "thinking", None)
        reply, used = CLIENT.chat_failover(
            model, messages, lethica.FAILOVER_CHAIN,
            temperature=lethica.TEMPERATURE, max_tokens=lethica.MAX_TOKENS,
            timeout=lethica.HTTP_TIMEOUT)
        if reply is None:
            return None, None
        reply = lethica.terse_filter(reply)
        last_reply = reply
        messages.append({"role": "assistant", "content": reply})
        out = lethica.dispatch(reply, lethica.SELF_PATH)
        if not out:
            final_text = lethica.strip_tags(reply)
            break
        if progress_cb:
            progress_cb(i, "tool", used)
        messages.append({"role": "user", "content": (
            "Tool results (lethica sandbox). Lanjut atau finalkan.\n\n<tool_response>\n"
            + _fmt_tool_results(out) + "\n</tool_response>"
        )})
    else:
        # v2.9.2 fix: dulu ambil messages[-1] (= tool_response mentah, bocor ke chat).
        # Sekarang pakai jawaban assistant terakhir yang beneran.
        final_text = lethica.strip_tags(last_reply or "")
    # trim conversation: keep system + last MAX_TURNS_STORED*2
    if len(messages) > MAX_TURNS_STORED * 2 + 1:
        messages[:] = [messages[0]] + messages[-(MAX_TURNS_STORED * 2):]
    return final_text, used


async def _agent_turn(chat_id, user_text, progress_cb=None):
    """Jalankan agent loop (sinkron, di thread executor) → return final text."""
    state = _chat(chat_id)
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        functools.partial(_run_agent_turn, state["messages"], state["model"],
                          user_text, progress_cb))


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


# ── Handlers ────────────────────────────────────────────────────────

HELP_TEXT = (
    "🤖 *Lethica* online — agent loop + tools via routerku\n\n"
    "Kirim chat bebas, aku jalankan agent (web\\_search, browse, memory, plan, rag, file, shell).\n\n"
    "/new — reset percakapan\n/model — info model aktif + failover chain\n"
    "/model &lt;nama&gt; — ganti model chat ini\n/status — statistik\n/help — ini")


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


async def on_text(update: Update, ctx):
    chat_id = update.effective_chat.id
    if AUTHORIZED is not None and chat_id not in AUTHORIZED:
        await update.message.reply_text("⛔ unauthorized.")
        return
    user_text = (update.message.text or "").strip()
    if not user_text:
        return
    await ctx.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    t0 = time.time()

    # pesan status progress (di-update tiap tool-round)
    status_msg = await update.message.reply_text("🤖 memproses…", parse_mode=None)
    last_edit = [0.0]

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
            _edit_or_send(update, status_msg, txt), ctx.application.loop)

    try:
        final, used = await _agent_turn(chat_id, user_text, _progress)
    except Exception as e:
        await _edit_or_send(update, status_msg, f"⚠ agent error: {e}"[:MAX_REPLY])
        return
    dt = time.time() - t0
    _save_state()
    if final is None:
        await _edit_or_send(update, status_msg, "✖ semua model gagal. Cek routerku /status.")
        return
    # strip tool tags dari display (jangan bocorin format tag ke chat)
    final = TOOL_TAG_RE.sub("", final).strip() or "(no content)"
    await _edit_or_send(update, status_msg, f"🤖 _{used} · {dt:.0f}s_\n\n{final}")


# ── Main ────────────────────────────────────────────────────────────

def main():
    _load_state()  # restore percakapan lintas restart
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("new", cmd_new))
    app.add_handler(CommandHandler("model", cmd_model))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    print("[lethica-bridge] starting @QMybotai_bot ...")
    app.run_polling(drop_pending_updates=True, allowed_updates=["message"])


if __name__ == "__main__":
    main()
