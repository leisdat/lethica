# core/loop.py — agent loop + slash commands (TUI)
import os
import re
import json
import time
import traceback

from rich.syntax import Syntax
from rich.live import Live
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt, Confirm
from rich.text import Text

from core import config, client as client_mod, tools, tags, ui, tokens, rag, soul, learning
from core.ui import console
from core.config import CFG  # noqa: F401  (backward-compat re-export)

SESSIONS_DIR = config.SESSIONS_DIR


def _new_messages():
    return [{"role": "system", "content": _refreshed_sysprompt()}]


def _refreshed_sysprompt():
    sysprompt = soul.build_system_prompt()
    last_snap = ui.load_latest_snapshot()
    if last_snap:
        sysprompt += f"\n\n## MEMORY HYDRATION (latest snapshot)\n{last_snap}\n"
    return sysprompt


def _last_assistant(messages):
    for mm in reversed(messages):
        if mm.get("role") == "assistant" and mm.get("content"):
            return mm["content"]
    return ""


def _panel(content, model="lethica"):
    return Panel(content, title=f"[bold yellow]🤖 lethica ({model})[/bold yellow]", border_style="yellow")


def _reflect(cl, model, messages, reply):
    """v2.7 reflection pass: verifier murah ngecek apakah jawaban final didukung bukti
    tool results. v2.8: pakai config.VERIFIER_MODEL kalau diset (model beda = no blind spot).
    Return 'OK' atau 'REVISE'."""
    ctx = []
    for m in messages[-8:]:
        c = m.get("content") or ""
        if m.get("role") == "user" and "<tool_response>" in c:
            ctx.append(c[:1500])
    if not ctx:
        return "OK"
    vmodel = config.VERIFIER_MODEL or model
    probe = [
        {"role": "system", "content": "Kamu verifier ketat. Bandingkan JAWABAN dengan BUKTI tool. "
                                      "Balas HANYA satu kata: OK kalau klaim didukung bukti, REVISE kalau ada klaim tanpa bukti/kontradiksi."},
        {"role": "user", "content": f"BUKTI:\n{'---'.join(ctx)}\n\nJAWABAN:\n{reply[:2000]}\n\nVerdict (OK/REVISE):"},
    ]
    r = cl.chat(vmodel, probe, temperature=0.0, max_tokens=700)
    verdict = ""
    finish = None
    if "error" not in r and r.get("choices"):
        ch = r["choices"][0]
        msg = ch.get("message") or {}
        verdict = (msg.get("content") or msg.get("reasoning_content") or "")
        finish = ch.get("finish_reason")
    verdict = (verdict or "").strip().upper()
    if "REVISE" in verdict:
        return "REVISE"
    if "OK" in verdict and finish == "stop":
        return "OK"
    # fallback: reasoning kepotong / kosong → scan kata kontradiksi di reasoning
    if any(w in verdict for w in ("KONTRADIKSI", "CONTRADICTION", "NOT SUPPORTED", "TIDAK DIDUKUNG", "TANPA BUKTI")):
        return "REVISE"
    return "OK"  # ambiguous → jangan loop ulang (biaya > manfaat)


def _active_client():
    """LClient dari provider aktif (v2.8.1 fix: dulu selalu DEFAULT_BASE=routerku
    meski /provider udah ganti → failover loop). Fallback ke default kalau provider rusak."""
    try:
        return client_mod.LClient.for_provider(config.ACTIVE_PROVIDER)
    except Exception:
        return client_mod.LClient()


def _output_truncated(cl, reply):
    """Deteksi output kepotong: finish_reason length, atau usage nyentuh max_tokens
    (free model sering bilang 'stop' padahal kepotong), atau code fence ganjil."""
    fr = getattr(cl, "last_finish_reason", None)
    if fr == "length":
        return True
    u = getattr(cl, "last_usage", None) or {}
    ct = u.get("completion_tokens") or 0
    if ct and ct >= int(config.MAX_TOKENS * 0.97):
        return True
    if not reply or len(reply) < 500:
        return False
    if reply.count("```") % 2 == 1:
        return True
    return False


def run_agent_turn(messages, model, max_rounds=None, client=None):
    """Satu agent turn: model → dispatch tools → loop. Return (final_reply, used_model).
    messages dimutasi in-place (user msg sudah ada di dalam).
    client: LClient aktif dari main loop (dibikin ulang oleh /provider)."""
    max_rounds = max_rounds or config.MAX_TOOL_ROUNDS
    max_cont = config.MAX_CONTINUE_ROUNDS
    cl = client or _active_client()
    learning.begin_turn()
    had_tools = False
    reply, used = None, None
    tool_rounds = 0
    cont_rounds = 0
    bad_rounds = 0
    while tool_rounds < max_rounds:
        turn_t0 = time.time()
        # hard budget guard (v2.8.6): stop kalau budget harian habis
        ok, msg = tokens.budget_ok()
        if not ok:
            console.print(f"[bold red]{msg}[/bold red]")
            return (reply, used) if reply else (None, None)
        elif msg:
            console.print(f"[bold yellow]{msg}[/bold yellow]")
        if config.STREAM:
            reply, used = _streamed_call(cl, model, messages)
            console.print()
        else:
            with console.status("[bold cyan]🧠 lethica analyzing...[/bold cyan]", spinner="dots2"):
                reply, used = cl.chat_failover(
                    model, messages, config.FAILOVER_CHAIN, timeout=config.HTTP_TIMEOUT)
        if reply is None:
            console.print(f"[bold red]✖ all models failed ({time.time()-turn_t0:.0f}s)[/bold red]")
            return None, None
        console.print(f"[dim]({used}, {time.time()-turn_t0:.0f}s)[/dim]")
        reply = ui.terse_filter(reply)
        # auto-continue kalau output kepotong (length / usage nyentuh max / fence ganjil)
        if _output_truncated(cl, reply):
            if cont_rounds >= max_cont:
                console.print("[dim yellow]⚠ truncation continue limit reached, finalizing[/dim yellow]")
            else:
                cont_rounds += 1
                learning.record_truncation()
                console.print(f"[dim yellow]⚠ output truncated → continue ({cont_rounds}/{max_cont})[/dim yellow]")
                messages.append({"role": "assistant", "content": reply})
                messages.append({"role": "user", "content": (
                    "⚠ Output kamu terpotong karena batas token. LANJUTKAN tepat dari akhir teks tadi "
                    "tanpa mengulang apa yang sudah ditulis, selesaikan task dan finalkan jawaban.")})
                continue
        tool_rounds += 1
        messages.append({"role": "assistant", "content": reply})
        display = tags.strip_tags(reply)
        if display and not config.STREAM:
            ui.render_md(display, f"[bold yellow]🤖 lethica ({used})[/bold yellow]")
        # v2.9.5: cuma bilang "executing tools" kalau reply MEMANG punya tool call
        _has_tag = bool(re.search(r"<(?:invoke|read_file|write_file|edit_file|list_dir|"
                                  r"search_content|http_request|download_file|web_search|browse|"
                                  r"memory|plan|rag|skill|task|tool_call)", reply or "", re.I))
        if _has_tag:
            console.print(f"[dim]⚙ executing tools for {used}...[/dim]")
        out = tags.dispatch(reply, config.SELF_PATH)
        if out:
            console.print("[dim green]✓ tools executed[/dim green]")
        if not out:
            # v2.9.5 safety-net: model kelihatan MAU panggil tool tapi formatnya gak
            # ke-parse (markup asing) → jangan balik ke prompt, minta ulang canonical.
            if tags.looks_like_tool_attempt(reply) and tool_rounds <= max_rounds:
                bad_rounds += 1
                if bad_rounds <= 3:
                    console.print(f"[dim yellow]⚠ tool call gak ke-parse → minta ulang canonical ({bad_rounds}/3)[/dim yellow]")
                    learning.record_truncation()
                    messages.append({"role": "user", "content": (
                        "⚠ Tool call kamu TIDAK ke-eksekusi: formatnya tidak dikenali dispatcher. "
                        "JANGAN ulangi markup itu. Pakai format canonical PERSIS ini:\n"
                        'Untuk perintah shell:\n<invoke name="antml:computer:execute_command">'
                        '<parameter name="command">PERINTAH</parameter></invoke>\n'
                        "Untuk file: <read_file path=\"/abs/path\" /> , "
                        "<write_file path=\"/abs/path\">ISI</write_file> , "
                        "<edit_file path=\"/abs/path\"><target>LAMA</target><replacement>BARU</replacement></edit_file> , "
                        "<list_dir path=\"/abs/path\" /> , "
                        "<search_content path=\"/abs/path\" pattern=\"regex\" />\n"
                        "Ulangi tool call yang sama sekarang dengan format di atas, tanpa narasi tambahan.")})
                    continue
                console.print("[dim yellow]⚠ tool call rusak berulang → finalisasi[/dim yellow]")
            if had_tools and _should_revise(cl, model, messages, reply):
                continue
            return reply, used
        had_tools = True
        messages.append({"role": "user", "content": (
            "Tool results (lethica sandbox, edit_file hanya di ~/lethica/, "
            "dangerous commands butuh confirm). Lanjut atau finalkan.\n\n<tool_response>\n"
            + out + "\n</tool_response>"
        )})
    # v2.9.5: loop berhenti karena LIMIT ronde (bukan karena model finalkan) → paksa finalisasi
    # biar user gak lihat "berhenti mendadak" tanpa jawaban.
    if reply:
        console.print(f"[dim yellow]⚠ max tool rounds ({max_rounds}) tercapai — finalisasi paksa[/dim yellow]")
        messages.append({"role": "user", "content": (
            f"Batas {max_rounds} ronde tool tercapai. Finalkan SEKARANG: ringkas hasil yang sudah "
            "didapat + sebutkan yang belum selesai. JANGAN panggil tool lagi.")})
        try:
            extra, used2 = cl.chat_failover(model, messages, config.FAILOVER_CHAIN, timeout=config.HTTP_TIMEOUT)
            if extra:
                reply, used = ui.terse_filter(extra), (used2 or used)
        except Exception:
            pass
        display = tags.strip_tags(reply)
        if display:
            ui.render_md(display, f"[bold yellow]🤖 lethica ({used})[/bold yellow]")
    return reply, used


def _streamed_call(cl, model, messages):
    """Streaming chat call dengan Live panel. Return (reply, used)."""
    buf = []

    def _cb(delta, kind):
        if kind == "reasoning":
            if config.SHOW_REASONING:
                console.print(f"[dim italic]{delta}[/dim italic]", end="")
        else:
            buf.append(delta)
            live.update(_panel(Text("".join(buf)), model), refresh=True)

    console.print(f"[dim]🧠 {model} ⟳ analyzing...[/dim]")
    with Live(_panel(Text(""), model), console=console, auto_refresh=False) as live:
        reply, used = cl.chat_failover(
            model, messages, config.FAILOVER_CHAIN,
            timeout=config.HTTP_TIMEOUT, stream_cb=_cb)
        display_final = tags.strip_tags("".join(buf))
        live.update(_panel(Markdown(display_final), model), refresh=True)
    return reply, used


def _should_revise(cl, model, messages, reply):
    """v2.7 reflection — cek jawaban final vs bukti tool. True = minta revisi."""
    try:
        verdict = _reflect(cl, model, messages, reply)
        learning.record_verdict(verdict)
    except Exception:
        return False
    if verdict != "REVISE":
        return False
    console.print("[dim]⟳ reflection: REVISE → lanjut round[/dim]")
    messages.append({"role": "user", "content": (
        "Reflection check menilai jawabanmu BELUM didukung bukti tool hasil tadi. "
        "Perbaiki: pakai ulang tool yang relevan atau koreksi klaim. "
        "Kalau memang sudah benar, finalkan jawaban yang sudah didukung bukti.")})
    return True


def apply_window(messages):
    """Sliding window dengan carry-over summary (v2.5: summary di-merge, gak degradasi berlapis).
    v2.7: tool_response besar (>2000 char) hanya head 2000 char yang dibawa (smart truncation)."""
    if len(messages) <= config.WINDOW_SIZE + 1:
        return messages
    dropped = messages[1:-config.WINDOW_SIZE]
    prev_summaries = [m for m in dropped if isinstance(m.get("content"), str)
                      and m.get("content", "").startswith("## Earlier context")]
    old = [m for m in dropped if not (isinstance(m.get("content"), str)
           and m.get("content", "").startswith("## Earlier context"))]
    parts = []
    # carry-over: summary lama dipertahankan apa adanya (gak re-truncate)
    for pm in prev_summaries:
        parts.append(pm["content"])
    for m in old:
        c = m.get("content") or ""
        cap = 300  # per-message summary cap default
        if m.get("role") == "user" and "<tool_response>" in c:
            # v2.7: tool_response besar → head pendek + marker (jangan potong lg biar marker kelihatan)
            head, sep, tail = c.partition("<tool_response>")
            inner, sep2, _ = tail.rpartition("</tool_response>")
            if len(inner) > 2000:
                inner = inner[:2000] + f"\n…(+{len(inner)-2000} chars, baca ulang via tool kalau perlu)"
                c = head + sep + inner + (sep2 if sep2 else "")
                cap = len(c)
        parts.append(f"[{m.get('role') or '?'}] {ui.terse_filter(c)[:cap]}")
    summary_msg = {"role": "user", "content": ("## Earlier context (carry-over)\n" + "\n".join(parts) + "\n## End of earlier context\n")}
    return [messages[0], summary_msg] + messages[-config.WINDOW_SIZE:]


# ── slash command handlers ──────────────────────────────────────────

def _cmd_save_load(user_input, cmd, messages, turn_counter, done_actions_log):
    """/save nama | /load nama (tanpa nama = list). Return messages (bisa diganti /load)."""
    parts = user_input.split(None, 1)
    action = parts[0].lower()
    name = re.sub(r"[^a-zA-Z0-9_\-]", "_", (parts[1] if len(parts) > 1 else "")).strip("_")[:60]
    sessions = sorted(f[:-5] for f in os.listdir(SESSIONS_DIR) if f.endswith(".json"))
    if action == "/save":
        if not name:
            name = time.strftime("session-%Y%m%d-%H%M%S")
        path = os.path.join(SESSIONS_DIR, name + ".json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"saved_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                       "turn": turn_counter[0], "messages": messages}, f, ensure_ascii=False, indent=1)
        console.print(f"[bold green]✓ session saved: {path} ({len(messages)} msgs)[/bold green]")
        return messages
    if not name:
        console.print(Panel("\n".join(sessions) or "(no sessions)",
                            title="[bold yellow]sessions[/bold yellow]", border_style="yellow"))
        return messages
    path = os.path.join(SESSIONS_DIR, name + ".json")
    if not os.path.isfile(path):
        console.print(f"[bold red]✗ session '{name}' not found. Available: {', '.join(sessions) or '(none)'}[/bold red]")
        return messages
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if len(messages) > 1:
        ui.save_snapshot(turn_counter[0], f"/load {name}", _last_assistant(messages), done_actions_log)
    messages = data.get("messages", [])
    turn_counter[0] = int(data.get("turn", 0))
    if messages and messages[0].get("role") == "system":
        messages[0] = {"role": "system", "content": _refreshed_sysprompt()}
    console.print(f"[bold green]✓ session loaded: {name} ({len(messages)} msgs, saved {data.get('saved_at', '?')})[/bold green]")
    return messages


def _persist_provider(pname):
    """Tulis provider aktif ke config.toml [model].provider + reload globals."""
    cfg_text = open(config.CONFIG_FILE, encoding="utf-8").read()
    if re.search(r"^\s*provider\s*=", cfg_text, re.M):
        cfg_text = re.sub(r'^\s*provider\s*=.*$', f'provider = "{pname}"', cfg_text, count=1, flags=re.M)
    else:
        cfg_text = cfg_text.replace("[model]", f'[model]\nprovider = "{pname}"', 1)
    with open(config.CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(cfg_text)
    config.reload_globals()


def _cmd_provider(cl, model):
    """/provider — switch/add provider. Return (cl, model) baru, atau (cl, model) lama kalau batal."""
    sel = ui.select_provider(current=config.ACTIVE_PROVIDER)
    if sel:
        pname = sel[0]
    else:
        r = ui.add_provider_interactive()
        if not r:
            return cl, model
        pname = r[0]
    config.ACTIVE_PROVIDER = pname
    _persist_provider(pname)
    p = config.get_provider(pname)
    cl = client_mod.LClient(base=p["base"], key=p["key"])
    # model default: dari daftar models provider kalau model lama gak ada
    try:
        avail = cl.models()
        if avail and model not in avail:
            model = avail[0]
            console.print(f"[yellow]model lama gak ada di provider ini → auto-switch ke {model}[/yellow]")
    except Exception:
        pass
    console.print(f"[bold green]✓ provider aktif: {pname} ({p['base']}) | model: {model}[/bold green]")
    return cl, model


def _cmd_config():
    """/config — tampil + optional edit config.toml, lalu reload."""
    console.print(Panel(config.CONFIG_FILE, title="[bold yellow]config file[/bold yellow]", border_style="yellow"))
    console.print(Syntax(open(config.CONFIG_FILE).read(), "toml", theme="monokai"))
    if Confirm.ask("Edit config sekarang?", default=False):
        import subprocess
        subprocess.run([os.environ.get("EDITOR", "nano"), config.CONFIG_FILE])
    config.reload_globals()
    console.print(f"[bold green]✓ config reloaded (persona: {config.PERSONA_MODE}, budget: {config.DAILY_BUDGET or 'off'})[/bold green]")


def _cmd_self():
    """/self — info source, core, backup, persona."""
    try:
        sz = os.path.getsize(config.SELF_PATH)
        with open(config.SELF_PATH) as f:
            lines = sum(1 for _ in f)
        mt = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(config.SELF_PATH)))
    except Exception as e:
        sz, lines, mt = "?", "?", str(e)
    core_files = []
    if os.path.isdir(config.CORE_DIR):
        core_files = sorted(f for f in os.listdir(config.CORE_DIR) if f.endswith(".py"))
    core_lines = sum(sum(1 for _ in open(os.path.join(config.CORE_DIR, f))) for f in core_files)
    from rich.table import Table
    t = Table(title=f"🧬 Lethica v{config.VERSION}", show_header=True, header_style="bold magenta")
    t.add_column("prop", style="cyan")
    t.add_column("val", style="green")
    t.add_row("source", f"{config.SELF_PATH} ({lines} ln)")
    t.add_row("core", f"{len(core_files)} modules, {core_lines} ln: {', '.join(core_files)}")
    t.add_row("backup", f"{'✓' if os.path.isfile(os.path.join(config.BACKUP_DIR, 'lethica.py.bak')) else '✗'} (refreshed on startup)")
    t.add_row("size", f"{sz/1024:.1f} KB" if isinstance(sz, int) else str(sz))
    t.add_row("modified", mt)
    t.add_row("persona", config.PERSONA_MODE)
    t.add_row("workspace", config.WORKSPACE)
    console.print(t)
    if os.path.isfile(config.CHANGELOG_FILE):
        console.print(Panel(open(config.CHANGELOG_FILE).read()[-2000:],
                            title="[bold yellow]changelog[/bold yellow]", border_style="yellow"))


MENU_TEXT = """[cyan]/menu[/cyan]     help
[cyan]/model[/cyan]    switch model
[cyan]/provider[/cyan] switch/add provider baru (v2.6)
[cyan]/history[/cyan]  show msg count
[cyan]/clear[/cyan]    reset conversation
[cyan]/restart[/cyan]  reload system prompt
[cyan]/self[/cyan]     show self info + changelog
[cyan]/config[/cyan]   show/edit config.toml + reload
[cyan]/tokens[/cyan]   token usage + budget (v2.5)
[cyan]/toolstats[/cyan] tool call stats sesi ini (v2.8)
[cyan]/learning[/cyan]  skor siluman + pelajaran + strategi (v2.9)
[cyan]/save[/cyan]     save session (/save nama)
[cyan]/load[/cyan]     load session (/load nama, tanpa nama = list)
[cyan]/improve[/cyan]  self-improvement mode
[cyan]/exit[/cyan]     bye"""


# ── main loop ───────────────────────────────────────────────────────

def main():
    os.chdir(config.WORKSPACE)
    ui.show_logo()
    cl = _active_client()
    model = ui.select_model(cl)
    ui.show_logo()
    console.print(Panel(
        Text.assemble(
            ("Status: ", "bold green"), ("ONLINE\n", "bold cyan"),
            ("Model: ", "bold green"), (f"{model}\n", "bold yellow"),
            ("Persona: ", "bold green"), (f"{config.PERSONA_MODE}\n", "bold cyan"),
            ("Sandbox: ", "bold green"), (f"{config.WORKSPACE}\n", "white"),
            ("Backend: ", "bold green"), (f"{config.DEFAULT_BASE}\n", "dim"),
        ),
        border_style="green",
    ))
    console.print("[dim]Slash: /menu /model /task /registry /experience /history /clear /restart /self /improve /config /tokens /exit[/dim]\n")

    # v2.5: refresh backup last-known-good tiap startup (backup selalu fresh)
    bak = tools.backup_self()
    if bak:
        console.print(f"[dim]✓ last-known-good backup: {bak}[/dim]")

    console.print(f"[dim]{rag.tool_rag('rebuild')}[/dim]")
    # v3.1: refresh kualitas task-memory (STALE/REUSABLE) dari bukti historis
    try:
        from core import experience
        n = experience.requality()
        if n:
            console.print(f"[dim]✓ experience requality: {n} memori di-update[/dim]")
    except Exception:
        pass
    # v3.5: semantic memory maintenance (consolidate + decay) — non-blocking
    try:
        from core import memory as semantic_mem
        c = semantic_mem.consolidate()
        d = semantic_mem.decay()
        if c or d:
            console.print(f"[dim]✓ v3.5 memory: consolidated={c} decayed={d}[/dim]")
    except Exception:
        pass
    # v3.6: knowledge graph maintenance — freshness reclassify + validasi (non-blocking)
    try:
        from core import world as world_mod, graph as graph_mod
        fr = world_mod.refresh()
        issues = graph_mod.validate()
        n_nodes = len(graph_mod._nodes())
        n_edges = len(graph_mod._edges())
        msg = (f"✓ v3.6 graph: {n_nodes} nodes/{n_edges} edges "
               f"stale={fr.get('stale', 0)} expired_edges={fr.get('expired_edges', 0)}")
        if not issues.get("ok"):
            msg += f"  issues={issues.get('counts')}"
        console.print(f"[dim]{msg}[/dim]")
    except Exception:
        pass
    messages = _new_messages()
    if ui.load_latest_snapshot():
        console.print("[dim]✓ hydrated from latest snapshot[/dim]")

    turn_counter = [0]
    done_actions_log = []

    while True:
        try:
            user_input = Prompt.ask("\n[bold magenta]➜ lethica>[/bold magenta]").strip()
            if not user_input:
                continue
            cmd = user_input.lower()
            turn_counter[0] += 1

            if cmd in ("exit", "quit", "/exit", "/quit"):
                if len(messages) > 1:
                    sp = ui.save_snapshot(turn_counter[0], user_input, _last_assistant(messages), done_actions_log)
                    console.print(f"[dim]snapshot saved: {sp}[/dim]")
                ui.save_history(messages)
                console.print("[bold magenta]Lethica signing off. Ttd, lethica.[/bold magenta]")
                break

            if cmd.startswith("/save") or cmd.startswith("/load"):
                messages = _cmd_save_load(user_input, cmd, messages, turn_counter, done_actions_log)
                continue

            if cmd == "/menu":
                console.print(Panel(MENU_TEXT, title="commands", border_style="magenta"))
                continue

            if cmd == "/model":
                model = ui.select_model(cl)
                console.print(f"[bold green]→ {model}[/bold green]")
                continue

            if cmd in ("/provider", "/prov", "/m/provider"):
                cl, model = _cmd_provider(cl, model)
                continue

            if cmd == "/history":
                u = sum(1 for m in messages if m["role"] == "user")
                a = sum(1 for m in messages if m["role"] == "assistant")
                console.print(f"[cyan]Total {len(messages)} | user {u} | assistant {a}[/cyan]")
                continue

            if cmd == "/tokens":
                console.print(tokens.summary_text())
                continue

            if cmd == "/toolstats":
                from core import stats
                console.print(Panel(stats.summary_text(), title="[bold cyan]tool usage (sesi ini)[/bold cyan]", border_style="cyan"))
                if config.VERIFIER_MODEL:
                    console.print(f"[dim]verifier: {config.VERIFIER_MODEL}[/dim]")
                continue

            if cmd == "/task":
                goal = user_input.split(None, 1)[1].strip() if len(user_input.split(None, 1)) > 1 else ""
                if not goal:
                    goal = Prompt.ask("[bold cyan]tujuan task (orchestrator multi-agent)[/bold cyan]").strip()
                if goal:
                    from core import orchestra
                    _t = orchestra.Task(goal, client=_active_client(), model=model)
                    orchestra.run(_t)
                    console.print(Panel(orchestra.report_text(_t), title=f"[bold cyan]🛰️ { _t.state}[/bold cyan]", border_style="cyan"))
                continue

            if cmd == "/experience":
                from core import experience
                sub = (user_input.split() + [""])[1].lower()
                if sub == "recall":
                    g = user_input.split(None, 2)[2] if len(user_input.split(None, 2)) > 2 else ""
                    import json as _j
                    console.print(_j.dumps(experience.recall(g), indent=1, ensure_ascii=False)[:3000])
                else:
                    console.print(Panel(experience.summary(), title="[bold cyan]🗺️ experience memory[/bold cyan]", border_style="cyan"))
                continue

            if cmd == "/registry":
                from core import registry
                console.print(Panel(registry.summary(), title="[bold cyan]📚 skill registry[/bold cyan]", border_style="cyan"))
                continue

            if cmd == "/learning":
                console.print(Panel(learning.summary_text(), title="[bold cyan]🧠 pembelajaran otomatis[/bold cyan]", border_style="cyan"))
                continue

            if cmd == "/config":
                _cmd_config()
                continue

            if cmd in ("/clear", "/restart", "/hapus"):
                if len(messages) > 1:
                    sp = ui.save_snapshot(turn_counter[0], "/clear", _last_assistant(messages), done_actions_log)
                    console.print(f"[dim]snapshot saved: {sp}[/dim]")
                messages = _new_messages()
                console.print("[bold green]✓ session reset (snapshot saved)[/bold green]")
                continue

            if cmd == "/self":
                _cmd_self()
                continue

            if cmd == "/improve":
                console.print(Panel(
                    f"[bold yellow]SELF-IMPROVEMENT MODE[/bold yellow]\n\n"
                    f"source : [cyan]{config.SELF_PATH}[/cyan] + core/\n"
                    f"backup : auto-refreshed tiap startup\n\n"
                    f"Describe the feature you want Lethica to gain:",
                    border_style="magenta"))
                req = Prompt.ask("[bold green]feature request[/bold green]").strip()
                if not req:
                    continue
                user_input = (
                    f"SELF-IMPROVEMENT MODE ACTIVE. User request: {req}\n\n"
                    f"Steps: 1) read source `<read_file path=\"{config.SELF_PATH}\" start=\"1\" end=\"400\" />` etc. "
                    f"2) edit via `<edit_file path=\"{config.SELF_PATH}\"><target>OLD</target><replacement>NEW</replacement></edit_file>`. "
                    f"3) verify: py_compile via execute_command. "
                    f"4) bump version in `{config.VERSION_FILE}` and append to `{config.CHANGELOG_FILE}`. "
                    f"5) tell user to /restart."
                )

            messages.append({"role": "user", "content": user_input})
            _auto_ground(messages)
            messages = apply_window(messages)
            learning.inject_strategy(messages)

            # budget warning (v2.5)
            bw = tokens.budget_warning()
            if bw:
                console.print(f"[bold yellow]{bw}[/bold yellow]")

            # auto-snapshot every 4 turns
            if turn_counter[0] % 4 == 0 and len(messages) > 1:
                sp = ui.save_snapshot(turn_counter[0], user_input, _last_assistant(messages), done_actions_log)
                console.print(f"[dim]auto-snapshot: {sp}[/dim]")

            final, used = run_agent_turn(messages, model, client=cl)
            _score, _action, _st = learning.end_turn(goal=user_input, reply=final or "")
            if _action == "abort":
                console.print(f"[bold red]✖ Skor Siluman {_score}% < {learning.ABORT_THRESHOLD}% — turn DIBATALKAN, hasil tidak dipercaya[/bold red]")
            elif _action == "correct":
                console.print(f"[bold yellow]⚠ Skor Siluman {_score}% < {learning.CORRECT_THRESHOLD}% — koreksi dicatat[/bold yellow]")
            else:
                console.print(f"[dim]✓ Skor Siluman {_score}%[/dim]")
            if final:
                for line in final.split("\n"):
                    if line.startswith("["):
                        done_actions_log.append(line[:200])
            ui.save_history(messages)
        except KeyboardInterrupt:
            ui.save_history(messages)
            console.print("\n[bold magenta]Session ended.[/bold magenta]")
            break
        except Exception as e:
            console.print(f"[bold red]error:[/bold red] {e}")
            traceback.print_exc()


def _auto_ground(messages):
    """v2.7 auto-grounding — inject konteks RAG relevan ke pesan user terakhir (v2.8: cached)."""
    user_input = messages[-1]["content"]
    try:
        gk = f"ground:{user_input[:200]}"
        g = getattr(rag, "_ground_cache", {}).get(gk)
        if g is None:
            g = rag.auto_ground(user_input)
            cache = getattr(rag, "_ground_cache", None)
            if cache is None:
                cache = {}
                setattr(rag, "_ground_cache", cache)
            cache[gk] = g
        if g:
            messages[-1]["content"] = user_input + "\n" + g
            console.print("[dim]⚡ grounded (auto-RAG)[/dim]")
    except Exception:
        pass
