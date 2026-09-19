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
import time

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
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


# ── Banner ──────────────────────────────────────────────────────────

def show_logo():
    sub = (f"[bold red]{config.PERSONA_MODE.upper()} • v{config.VERSION} • "
           "config.toml • web/browser/memory/plan/rag • routerku-powered[/bold red]")
    console.print(Panel(
        Text(LOGO, style="bold magenta", justify="center"),
        title=f"[bold cyan]Lethica v{config.VERSION}[/bold cyan]",
        subtitle=sub,
        border_style="red",
    ))


# ── Provider / model selectors ──────────────────────────────────────

def select_provider(current=None):
    """TUI selector provider dari config.toml. Return (name, provider_dict) atau None kalau cancel."""
    names = config.provider_names()
    if not names:
        console.print("[bold red]Gak ada provider di config.toml [providers.*][/bold red]")
        return None

    table = Table(title="🔌 Providers (config.toml)", show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Provider", style="green")
    table.add_column("Base", style="dim")
    for i, n in enumerate(names, 1):
        p = config.get_provider(n)
        mark = " ← aktif" if n == current else ""
        table.add_row(str(i), f"{n}{mark}", p["base"])
    table.add_row(str(len(names) + 1), "[white]✏ add new…[/white]", "")
    console.print(table)

    choice = Prompt.ask(f"[bold yellow]Pick provider (1-{len(names) + 1})[/bold yellow]", default="1")
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


def select_model(client):
    console.print(f"\n[bold cyan]Scanning models dari [yellow]{client.base}[/yellow]...[/bold cyan]")
    try:
        models = client.models()
    except Exception as e:
        console.print(f"[bold red]Fetch failed: {e}[/bold red]")
        models = [config.DEFAULT_MODEL]
    models = [m for m in models if m][:20]

    table = Table(title="📚 Available Models", show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Model", style="green")
    for i, m in enumerate(models, 1):
        table.add_row(str(i), m)
    table.add_row(str(len(models) + 1), "[white]✏ custom name[/white]")
    console.print(table)

    choice = Prompt.ask(f"[bold yellow]Pick model (1-{len(models) + 1})[/bold yellow]", default="1")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            return models[idx]
        if idx == len(models):
            return Prompt.ask("[bold yellow]Custom model name[/bold yellow]")
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

def render_md(text, title):
    console.print(Panel(Markdown(text), title=title, border_style="yellow"))
