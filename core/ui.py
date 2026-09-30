# core/ui.py — logo, tables, select_model, terse_filter, snapshots
#
# Struktur:
#   console + LOGO      — rich console & banner
#   show_logo           — panel header TUI
#   select_provider / add_provider_interactive / select_model — setup TUI
#   terse_filter        — mode 4: strip policy wrappers + politeness prefix
#   snapshots           — save/load snapshot (mode 3)
#   history             — load/save conversation history
#   render_md           — panel markdown

import json
import os
import re
import sys
import time

from rich import box
from rich.console import Console
from rich.console import Group
from rich.markdown import Markdown
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.prompt import Prompt

from core import config

console = Console()

LOGO = """\
 ██╗     ███████╗████████╗██╗  ██╗██╗ ██████╗ █████╗
 ██║     ██╔════╝╚══██╔══╝██║  ██║██║██╔════╝██╔══██╗
 ██║     █████╗     ██║   ███████║██╗  ██║██╗ ███████╗
 ██║     ██╔══╝     ██║   ██╔══██║██║██║     ██╔══██║
 ███████╗███████╗   ██║   ██║  ██║██║╚██████╗██║  ██║
 ╚══════╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝
"""


# ── v3.8 theme tokens (satu sumber warna, biar konsisten & gampang diganti) ──
THEME = {
    "brand": "magenta",
    "accent": "cyan",
    "ok": "green",
    "warn": "yellow",
    "err": "red",
    "muted": "dim",
    "user": "bright_white",
}


def c(key):
    """Ambil warna tema; fallback 'white' kalau key salah."""
    return THEME.get(key, "white")


# ── v3.8 command registry (satu sumber: /help + tab-completion + /menu) ──
# (cmd, arg, desc). Tambah di sini → otomatis muncul di /help DAN completion.
COMMANDS = [
    ("/menu", "", "help ringkas (alias /help)"),
    ("/model", "", "ganti model aktif"),
    ("/provider", "", "ganti / tambah provider"),
    ("/task", "<goal>", "orchestrator multi-agent"),
    ("/registry", "", "skill registry"),
    ("/experience", "[recall <goal>]", "memory pengalaman"),
    ("/learning", "", "skor siluman + strategi"),
    ("/tokens", "", "token usage + budget"),
    ("/toolstats", "", "statistik tool sesi ini"),
    ("/history", "", "jumlah pesan di konteks"),
    ("/save", "[nama]", "simpan sesi"),
    ("/load", "[nama]", "muat sesi"),
    ("/clear", "", "reset percakapan"),
    ("/restart", "", "reload system prompt"),
    ("/self", "", "info source + changelog"),
    ("/config", "", "lihat / edit config.toml"),
    ("/improve", "", "self-improvement mode"),
    ("/exit", "", "keluar"),
]
_CMD_NAMES = [x[0] for x in COMMANDS]


def help_table():
    """Tabel command rapi (dipakai /menu & /help). Lebar aman di 80 kolom."""
    t = Table(box=box.SIMPLE_HEAD, show_header=True, header_style=f"bold {c('brand')}",
              border_style=c('muted'), padding=(0, 1), expand=False)
    t.add_column("cmd", style=c("accent"), no_wrap=True)
    t.add_column("arg", style=c("muted"), no_wrap=True)
    t.add_column("fungsi", style="white")
    for cmd, arg, desc in COMMANDS:
        t.add_row(cmd, arg, desc)
    return t


# ── Banner ──────────────────────────────────────────────────────────

def show_logo(model=None):
    """Banner. Mode dari config.BANNER: 'compact' (default) | 'full' | 'off'."""
    mode = str(getattr(config, "BANNER", "compact") or "compact").lower()
    if mode == "off":
        return
    if mode == "full":
        sub = (f"[bold {c('err')}]{config.PERSONA_MODE.upper()} • v{config.VERSION} • "
               "config.toml • web/browser/memory/plan/rag • routerku-powered[/bold red]")
        console.print(Panel(
            Text(LOGO, style=f"bold {c('brand')}", justify="center"),
            title=f"[bold {c('accent')}]Lethica v{config.VERSION}[/bold {c('accent')}]",
            subtitle=sub,
            border_style=c("err"),
        ))
        return
    # compact: 1 baris, hemat ruang vertikal di HP
    brand = Text()
    brand.append("◆ lethica ", style=f"bold {c('brand')}")
    brand.append(f"v{config.VERSION}", style=c("muted"))
    brand.append("  •  ", style=c("muted"))
    brand.append(str(config.PERSONA_MODE), style=c("accent"))
    if model:
        brand.append("  •  ", style=c("muted"))
        brand.append(str(model), style=c("ok"))
    console.print(brand)


def status_line(model=None, extra=None):
    """Satu baris status pengganti panel 6-baris (v3.8)."""
    parts = []
    if model:
        parts.append(f"[{c('ok')}]{model}[/{c('ok')}]")
    parts.append(f"[{c('muted')}]{config.ACTIVE_PROVIDER}[/{c('muted')}]")
    parts.append(f"[{c('muted')}]{config.WORKSPACE}[/{c('muted')}]")
    if extra:
        parts.append(f"[{c('muted')}]{extra}[/{c('muted')}]")
    console.print("  ".join(parts))


def startup_summary(items):
    """Ringkas log maintenance startup jadi SATU baris (v3.8).
    VERBOSE=true → satu baris per item (buat debugging)."""
    items = [str(i) for i in (items or []) if i]
    if not items:
        return
    if getattr(config, "VERBOSE", False):
        for it in items:
            console.print(f"[{c('muted')}]· {it}[/{c('muted')}]")
        return
    console.print(f"[{c('muted')}]✓ {' · '.join(items)}[/{c('muted')}]")


# ── v3.8 input layer: history + tab-completion + prompt rapi ─────────

_HISTORY_FILE = os.path.join(config.LETHICA_DIR, ".lethica_history")


def _completer(text, state):
    if state == 0:
        _completer.matches = [n for n in _CMD_NAMES if n.startswith(text)]
    try:
        return _completer.matches[state]
    except IndexError:
        return None


def setup_readline():
    """Aktifkan history (↑/↓) + tab-completion command. Non-fatal kalau gak ada readline."""
    try:
        import readline
        try:
            readline.read_history_file(_HISTORY_FILE)
        except Exception:
            pass
        readline.set_history_length(500)
        readline.set_completer(_completer)
        readline.set_completer_delims(" \t\n")
        readline.parse_and_bind("tab: complete")
        return True
    except Exception:
        return False


def save_readline():
    try:
        import readline
        readline.write_history_file(_HISTORY_FILE)
    except Exception:
        pass


def ask_prompt(model=None, turn=None):
    """Prompt input readline-aware. ANSI, BUKAN rich markup: input() mencetak
    prompt mentah apa adanya (markup rich bakal muncul literal)."""
    tag = f"lethica:{turn}" if turn is not None else "lethica"
    if sys.stdout.isatty():
        # \001..\002 = marker "invisible" → readline hitung lebar prompt dgn benar
        prompt = (f"\001\033[1;35m\002➜ {tag}\001\033[0m\002 "
                  f"\001\033[35m\002›\001\033[0m\002 ")
    else:
        prompt = "lethica> "
    try:
        return input(prompt)
    except EOFError:
        return "/exit"


def err(msg, exc=None):
    """Error ringkas. Traceback cuma kalau VERBOSE=true."""
    console.print(f"[bold {c('err')}]✗ {msg}[/bold {c('err')}]")
    if exc is not None and getattr(config, "VERBOSE", False):
        import traceback
        console.print(f"[{c('muted')}]{traceback.format_exc()}[/{c('muted')}]")


def tool_line(labels, ok=True, limit=6):
    """Satu baris ringkas aksi tool: ⚙ read_file · search_content ✓ (v3.8)."""
    labels = [str(x) for x in (labels or []) if x]
    if not labels:
        return
    shown = " · ".join(labels[:limit])
    more = f" +{len(labels) - limit}" if len(labels) > limit else ""
    mark = f"[{c('ok')}]✓[/{c('ok')}]" if ok else f"[{c('err')}]✗[/{c('err')}]"
    console.print(f"[{c('muted')}]⚙ {shown}{more}[/{c('muted')}] {mark}")


# ── Provider / model selectors ──────────────────────────────────────

def select_provider(current=None):
    """TUI selector provider dari config.toml. Return (name, provider_dict) atau None kalau cancel."""
    names = config.provider_names()
    if not names:
        console.print("[bold red]Gak ada provider di config.toml [providers.*][/bold red]")
        return None

    table = Table(title="🔌 Providers (config.toml)", box=box.SIMPLE_HEAD,
                  show_header=True, header_style=f"bold {c('brand')}",
                  border_style=c("muted"), padding=(0, 1))
    table.add_column("#", style=c("accent"), width=3, no_wrap=True)
    table.add_column("Provider", style=c("ok"), no_wrap=True)
    table.add_column("Base", style=c("muted"), overflow="fold")
    for i, n in enumerate(names, 1):
        p = config.get_provider(n)
        mark = " ← aktif" if n == current else ""
        table.add_row(str(i), f"{n}{mark}", p["base"])
    table.add_row(str(len(names) + 1), "[white]✏ add new…[/white]", "")
    console.print(table)

    choice = Prompt.ask(f"[bold {c('warn')}]Pick provider (1-{len(names) + 1}, Enter=batal)[/bold {c('warn')}]",
                        default="")
    if not choice.strip():
        return None
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(names):
            n = names[idx]
            return n, config.get_provider(n)
    except Exception:
        pass
    return None


def add_provider_interactive():
    """Tambah provider baru via prompt → langsung di-save ke config.toml."""
    console.print("[bold cyan]Add new provider[/bold cyan]")
    name = Prompt.ask("[bold yellow]Name[/bold yellow]").strip().lower().replace(" ", "-")
    if not name:
        return None
    base = Prompt.ask("[bold yellow]Base URL[/bold yellow]").strip().rstrip("/")
    key = Prompt.ask("[bold yellow]API key[/bold yellow]", password=True).strip()
    models_raw = Prompt.ask(
        "[bold yellow]Models (comma-separated, optional, kosong=auto-detect)[/bold yellow]").strip()
    if not base:
        console.print("[bold red]base wajib[/bold red]")
        return None

    block = _provider_toml_block(name, base, key, models_raw)
    replaced = _upsert_provider_block(name, block)
    if replaced:
        console.print(f"[yellow]provider '{name}' sudah ada → replace[/yellow]")

    config.reload_globals()
    p = config.get_provider(name)
    console.print(f"[bold green]✓ provider '{name}' saved → {base}[/bold green]")
    _probe_provider(p)
    return name, p


def _provider_toml_block(name, base, key, models_raw):
    lines = [f"[providers.{name}]", f'base = "{base}"', f'key = "{key}"']
    if models_raw:
        models = [m.strip() for m in models_raw.split(",") if m.strip()]
        lines.append(f"models = {models!r}".replace("'", '"'))
    return "\n".join(lines)


def _upsert_provider_block(name, block):
    """Insert/replace section [providers.<name>] di config.toml. Return True kalau replace."""
    with open(config.CONFIG_FILE, encoding="utf-8") as f:
        cfg_text = f.read()

    out, skip, replaced = [], False, False
    for ln in cfg_text.split("\n"):
        if skip:
            if ln.startswith("["):
                skip = False  # next section mulai → berhenti skip
            else:
                continue
        if not replaced and ln.strip() == f"[providers.{name}]":
            out.append(block)
            skip = replaced = True
            continue
        out.append(ln)

    if replaced:
        cfg_text = "\n".join(out)
    else:
        cfg_text = cfg_text.rstrip("\n") + "\n\n" + block + "\n"

    with open(config.CONFIG_FILE, "w", encoding="utf-8") as f:
        f.write(cfg_text)
    return replaced


def _probe_provider(p):
    """Cek koneksi provider baru (GET /models)."""
    from core import client as _cl
    probe = _cl.LClient(base=p["base"], key=p["key"])
    test = probe._req("GET", "/models")
    if "error" in test:
        console.print(f"[yellow]⚠ probe gagal (code {test['error'].get('code')}) — cek base/key[/yellow]")
    else:
        n_models = len(test.get("data") or [])
        console.print(f"[bold green]✓ probe OK — {n_models} model tersedia[/bold green]")


def select_model(client, current=None, auto=False):
    """Pilih model.
    auto=True  (startup)  → pakai `current`/DEFAULT_MODEL tanpa scan jaringan +
                            prompt. Hemat 1 request + waktu tiap start (v3.8).
    auto=False (/model)   → scan provider + tabel interaktif."""
    if auto:
        return current or config.DEFAULT_MODEL
    console.print(f"\n[bold cyan]Scanning models dari [yellow]{client.base}[/yellow]...[/bold cyan]")
    try:
        models = client.models()
    except Exception as e:
        console.print(f"[bold red]Fetch failed: {e}[/bold red]")
        models = [config.DEFAULT_MODEL]
    models = [m for m in models if m][:20]

    table = Table(title="📚 Available Models", box=box.SIMPLE_HEAD,
                  show_header=True, header_style=f"bold {c('brand')}",
                  border_style=c("muted"), padding=(0, 1))
    table.add_column("#", style=c("accent"), width=3, no_wrap=True)
    table.add_column("Model", style=c("ok"), overflow="fold")
    for i, m in enumerate(models, 1):
        table.add_row(str(i), m)
    table.add_row(str(len(models) + 1), "[white]✏ custom name[/white]")
    console.print(table)

    choice = Prompt.ask(f"[bold {c('warn')}]Pick model (1-{len(models) + 1}, Enter=keep)[/bold {c('warn')}]",
                        default="")
    if not choice.strip():
        return current or (models[0] if models else config.DEFAULT_MODEL)
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            return models[idx]
        if idx == len(models):
            return Prompt.ask(f"[bold {c('warn')}]Custom model name[/bold {c('warn')}]")
    except Exception:
        pass
    return models[0] if models else config.DEFAULT_MODEL


# ── Mode 4: terse filter ────────────────────────────────────────────

DROP_PATTERNS = [
    r"<system-reminder>.*?</system-reminder>",
    r"\[SystemNote\].*?\[/SystemNote\]",
    r"\[ContentFiltered\]",
    r"\[Refused\]",
    r"<redacted>.*?</redacted>",
    r"I'm sorry,? but[^.]{0,100}\.",
    r"As an? (AI|language model|assistant)[^.]{0,80}\.",
    r"I (don't|do not) have the ability to[^.]{0,80}\.",
    r"I('m| am) (not able|unable|not allowed)[^.]{0,80}\.",
    # v2.9.2 fix: politeness prefix WAJIB anchored ke awal baris + word-boundary.
    # Dulu r"Sure!?\s*" (IGNORECASE) nge-strip substring di tengah kata:
    # "ensure safety" → "ensafety", "make sure it works" → "make it works".
    r"(?m)^[ \t]*Sure!?[ \t]*",
    r"(?m)^[ \t]*Of course!?[ \t]*",
    r"(?m)^[ \t]*I'd be happy to[^.]{0,40}\.[ \t]*",
]

_DROP_RE = [re.compile(p, re.DOTALL | re.IGNORECASE) for p in DROP_PATTERNS]


def terse_filter(text):
    """Mode 4: strip policy wrappers + politeness prefix biar irit token."""
    if not text or not isinstance(text, str):
        return ""
    out = text
    for rx in _DROP_RE:
        out = rx.sub("", out)
    return out.strip()


# ── Mode 3: snapshots ───────────────────────────────────────────────

def save_snapshot(turn_idx, user_intent, last_assistant, done_actions):
    try:
        intent = user_intent or "(no intent)"
        reply = last_assistant or "(no reply yet)"
        actions = done_actions or []
        snap = f"""# Snapshot turn-{turn_idx}
## Goal
{intent}

## Last assistant reply
{reply[:2000]}

## Done this turn
{chr(10).join('- ' + str(a) for a in actions[-20:]) or '(none)'}

## Generated
{time.strftime('%Y-%m-%d %H:%M:%S')}
"""
        path = os.path.join(config.SNAPSHOT_DIR, f"turn-{turn_idx:04d}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(snap)
        return path
    except Exception as ex:
        return f"snapshot_err: {ex}"


def load_latest_snapshot():
    try:
        files = sorted(
            [f for f in os.listdir(config.SNAPSHOT_DIR)
             if f.startswith("turn-") and f.endswith(".md")],
            reverse=True,
        )
        if not files:
            return None
        with open(os.path.join(config.SNAPSHOT_DIR, files[0]), encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


# ── History ─────────────────────────────────────────────────────────

def load_history():
    if not os.path.isfile(config.HISTORY_FILE):
        return []
    try:
        with open(config.HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_history(messages):
    try:
        with open(config.HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    except Exception as e:
        console.print(f"[dim yellow]⚠ history save failed: {e}[/dim yellow]")


# ── Render ──────────────────────────────────────────────────────────

def _assistant_title(model):
    t = Text()
    t.append("lethica", style=f"bold {c('brand')}")
    t.append(f" · {model}", style=c("muted"))
    return t


def assistant_panel(text, model="lethica", footer=None):
    """Panel standar respons asisten: judul konsisten, border tema, padding lega,
    footer opsional (mis. '8s · 1.2k tokens'). Satu sumber — jangan hardcode
    judul panel di call site lagi."""
    sub = Text(footer, style=c("muted"), justify="right") if footer else None
    console.print(Panel(Markdown(text), title=_assistant_title(model), subtitle=sub,
                        border_style=c("accent"), padding=(1, 2)))


def live_panel(content, model="lethica"):
    """Panel (tanpa print) buat Live streaming — gaya sama kayak assistant_panel."""
    return Panel(content, title=_assistant_title(model),
                 border_style=c("accent"), padding=(1, 2))


def render_md(text, model="lethica", footer=None):
    assistant_panel(text, model, footer)


# ── Status helpers (satu sumber warna, ganti console.print berserakan) ──

def ok(msg):
    console.print(f"[{c('ok')}]✓ {msg}[/{c('ok')}]")


def warn(msg):
    console.print(f"[{c('warn')}]⚠ {msg}[/{c('warn')}]")


def info(msg):
    console.print(f"[{c('muted')}]· {msg}[/{c('muted')}]")


def fail(msg):
    console.print(f"[bold {c('err')}]✗ {msg}[/bold {c('err')}]")
