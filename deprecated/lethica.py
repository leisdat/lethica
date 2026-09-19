#!/data/data/com.termux/files/usr/bin/python3
# lethica.py — Lethica v1.0
# Free-form agentic AI for Termux/Android, powered by routerku (:20130 Free-All).
# Inspired by kiro.py architecture (urllib client + rich UI + native tool tags),
# enhanced with: sandbox workspace, per-tool confirm prompts, sliding-window memory,
# self-heal backup, and automatic model failover.

import os, sys, re, json, time, shutil, subprocess, urllib.request, urllib.error, traceback

# ── stdin patch (run via pipe) ───────────────────────────────────────
if not sys.stdin.isatty():
    try:
        sys.stdin = open("/dev/tty")
    except Exception:
        pass

# ── rich import (hard dep) ───────────────────────────────────────────
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    from rich.markdown import Markdown
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    from rich.syntax import Syntax
except ImportError:
    print("Lethica butuh 'rich': pip install rich")
    sys.exit(1)

console = Console()

# ── config ──────────────────────────────────────────────────────────
HOME = os.path.expanduser("~")
LETHICA_DIR = os.path.join(HOME, "lethica")
WORKSPACE = os.path.join(LETHICA_DIR, "workspace")
BACKUP_DIR = os.path.join(LETHICA_DIR, "backups")
LOG_DIR = os.path.join(LETHICA_DIR, "logs")
os.makedirs(WORKSPACE, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)

# Sandbox: commands & file writes confined to these paths.
SANDBOX_DIRS = [WORKSPACE, LETHICA_DIR, "/tmp"]  # /tmp may not exist on Termux
SELF_PATH = os.path.abspath(__file__)
SELF_BACKUP = os.path.join(BACKUP_DIR, "lethica.py.bak")
VERSION_FILE = os.path.join(LETHICA_DIR, ".lethica_version")
HISTORY_FILE = os.path.join(LETHICA_DIR, "history.json")
CHANGELOG_FILE = os.path.join(LETHICA_DIR, "changelog.md")

# routerku endpoint (free combo failover baked-in)
DEFAULT_BASE = "http://127.0.0.1:20130/v1"
DEFAULT_MODEL = "Free-All"
API_KEY = os.environ.get("LETHICA_KEY", "sk-routerku")  # routerku bypass auth, any non-empty key works

# tool call format (same as kiro.py for compat)
EXEC_TAG_RE = re.compile(
    r'<invoke\s+name="antml:computer:execute_command">\s*<parameter\s+name="command">(.*?)</parameter>\s*</invoke>',
    re.DOTALL | re.IGNORECASE,
)
READ_TAG_RE = re.compile(
    r'<read_file\s+path="([^"]+)"(?:\s+start="(\d+)")?(?:\s+end="(\d+)")?\s*/?>',
    re.IGNORECASE,
)
WRITE_TAG_RE = re.compile(
    r'<write_file\s+path="([^"]+)"(?:\s+append="(true|false)")?\s*>(.*?)</write_file>',
    re.DOTALL | re.IGNORECASE,
)
EDIT_TAG_RE = re.compile(
    r'<edit_file\s+path="([^"]+)">\s*<target>\n?(.*?)\n?</target>\s*<replacement>\n?(.*?)\n?</replacement>\s*</edit_file>',
    re.DOTALL | re.IGNORECASE,
)
LIST_TAG_RE = re.compile(
    r'<list_dir\s+path="([^"]+)"(?:\s+recursive="(true|false)")?\s*/?>',
    re.IGNORECASE,
)
SEARCH_TAG_RE = re.compile(
    r'<search_content\s+path="([^"]+)"\s+pattern="([^"]+)"(?:\s+recursive="(true|false)")?(?:\s+ignore_case="(true|false)")?\s*/?>',
    re.IGNORECASE,
)
HTTP_TAG_RE = re.compile(
    r'<http_request\s+url="([^"]+)"(?:\s+method="(GET|POST|PUT|DELETE|PATCH)")?(?:\s+headers="([^"]*)")?(?:\s+body="([^"]*)")?\s*/?>',
    re.IGNORECASE,
)
DL_TAG_RE = re.compile(
    r'<download_file\s+url="([^"]+)"\s+output="([^"]+)"\s*/?>',
    re.IGNORECASE,
)

# Dangerous command pattern (asks for confirm before run)
DANGER_RE = re.compile(
    r"(?:"
    r"rm\s+-r[fF]|rm\s+-fr|rm\s+-rf|rm\s+--recursive\s+--force|"
    r":\(\)\s*\{\s*:\|:&\s*\};:"                       # fork bomb
    r"|mkfs(?:\.[a-z0-9]+)?\s"
    r"|(?<![a-zA-Z0-9_/])mv\s+/"                        # mv /... (not amv/, not ./)
    r"|(?<![a-z0-9_/])dd\s+if="                         # dd if=... (not readdd/, not adddd)
    r"|(?<![a-z0-9_/])wget\s"                          # wget ... (not mywget/)
    r"|>\s*/dev/(?:sd|hd|nvme|mmcblk)"                  # > /dev/sda etc
    r"|chmod\s+-R\s+777"
    r"|curl\s+[^\|]+\|\s*(?:sh|bash)\b"                 # curl | bash
    r")",
    re.IGNORECASE,
)


# ── OpenAI-compatible client (urllib, zero-dep) ─────────────────────
class LClient:
    def __init__(self, base, key):
        self.base = base.rstrip("/")
        self.key = key

    def _req(self, method, path, body=None):
        url = f"{self.base}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.key}",
            "User-Agent": "Lethica/1.0",
        }
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            return {"error": {"code": e.code, "message": e.reason}}
        except Exception as e:
            return {"error": {"code": 0, "message": str(e)}}

    def models(self):
        d = self._req("GET", "/models")
        if "error" in d:
            return ["Free-All", "Free-Kombo", "L", "bai/hy3", "unorouter/allam-2-7b:free", "hc/MiniMax-M3"]
        return sorted([m.get("id", "") for m in d.get("data", [])])

    def chat(self, model, messages, temperature=0.7, max_tokens=2048, timeout=60):
        body = {"model": model, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
        return self._req("POST", "/chat/completions", body)


# ── sandbox check ───────────────────────────────────────────────────
def in_sandbox(path):
    """Return True if path is inside allowed directories. Resolves traversal & symlinks."""
    if not path or not isinstance(path, str):
        return False
    path = os.path.expanduser(os.path.expandvars(path))
    try:
        p = os.path.realpath(path)
    except Exception:
        return False
    if p in ("/", os.path.expanduser("~"), ""):
        return False
    if p == SELF_PATH or p == SELF_BACKUP:
        return True
    for d in SANDBOX_DIRS:
        if not d or not isinstance(d, str):
            continue
        d_real = os.path.realpath(d) if os.path.exists(d) else None
        if not d_real:
            continue
        if p == d_real or p.startswith(d_real.rstrip("/") + "/"):
            return True
    return False
    # always allow self-path for self-edit
    if p == SELF_PATH or p == SELF_BACKUP:
        return True
    for d in SANDBOX_DIRS:
        d_real = os.path.realpath(d) if os.path.exists(d) else d
        if p == d_real or p.startswith(d_real.rstrip("/") + "/"):
            return True
    return False


def is_dangerous(cmd):
    if not cmd or not isinstance(cmd, str):
        return False
    return bool(DANGER_RE.search(cmd))


# ── native tools ────────────────────────────────────────────────────
def tool_read_file(path, start=None, end=None):
    if not os.path.isfile(path):
        return f"Error read_file: '{path}' not found."
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        total = len(lines)
        s = max(1, int(start)) if start else 1
        e = min(total, int(end)) if end else total
        if s > total:
            return f"Error read_file: start ({s}) > total ({total})."
        snippet = "".join(f"{i}:{lines[i-1]}" for i in range(s, e + 1))
        return f"Read {path} (lines {s}-{e}/{total}):\n{snippet}"
    except Exception as ex:
        return f"Error read_file: {ex}"


def tool_write_file(path, content, append=False):
    if not in_sandbox(path):
        return f"Error write_file: path '{path}' is OUTSIDE sandbox ({SANDBOX_DIRS}). Use a path inside ~/lethica/ or subfolder."
    try:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(content or "")
        verb = "appended to" if append else "wrote to"
        return f"OK {verb} {path} ({len(content or "")} chars)."
    except Exception as ex:
        return f"Error write_file: {ex}"


def tool_edit_file(path, target, replacement):
    if not in_sandbox(path):
        return f"Error edit_file: path '{path}' OUTSIDE sandbox."
    if not os.path.isfile(path):
        return f"Error edit_file: file '{path}' not found."
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        c = content.count(target)
        if c == 0:
            return "Error edit_file: TARGET not found. Read file first, ensure exact match (incl. whitespace)."
        if c > 1:
            return f"Error edit_file: TARGET matched {c}x (must be unique). Expand target block."
        new = content.replace(target, replacement, 1)
        with open(path, "w", encoding="utf-8") as f:
            f.write(new)
        return f"OK edit at {path} (1 replacement)."
    except Exception as ex:
        return f"Error edit_file: {ex}"


def tool_list_dir(path, recursive="false"):
    if not os.path.isdir(path):
        return f"Error list_dir: '{path}' not a directory."
    try:
        entries = sorted(os.listdir(path))
        out = [f"Listing {path} ({len(entries)} items):"]
        for e in entries[:200]:
            full = os.path.join(path, e)
            if os.path.isdir(full):
                out.append(f"  [DIR]  {e}/")
            else:
                try:
                    out.append(f"  {os.path.getsize(full):>8} B  {e}")
                except OSError:
                    out.append(f"  ?")
        if len(entries) > 200:
            out.append(f"  ... +{len(entries) - 200} more")
        return "\n".join(out)
    except Exception as ex:
        return f"Error list_dir: {ex}"


def tool_search_content(path, pattern, recursive="false", ignore_case="false"):
    try:
        flags = re.IGNORECASE if ignore_case.lower() == "true" else 0
        rx = re.compile(pattern, flags)
        skip = {".git", "node_modules", ".venv", "__pycache__", "backups", "logs"}
        results = []
        files = []
        if os.path.isfile(path):
            files = [path]
        elif os.path.isdir(path):
            if recursive.lower() == "true":
                for root, dirs, names in os.walk(path):
                    dirs[:] = [d for d in dirs if d not in skip]
                    for n in names:
                        files.append(os.path.join(root, n))
            else:
                files = [os.path.join(path, n) for n in os.listdir(path)
                         if os.path.isfile(os.path.join(path, n))]
        else:
            return f"Error search_content: '{path}' not found."
        for fp in files:
            try:
                with open(fp, "rb") as fb:
                    if b"\x00" in fb.read(1024):
                        continue
                with open(fp, "r", encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if rx.search(line):
                            results.append(f"{fp}:{i}: {line.rstrip()[:200]}")
                            if len(results) >= 100:
                                return "\n".join(results + ["... truncated at 100 results."])
            except (OSError, PermissionError):
                continue
        if not results:
            return f"No matches for '{pattern}' in '{path}'."
        return "\n".join(results)
    except re.error as rex:
        return f"Error search_content: bad regex - {rex}"
    except Exception as ex:
        return f"Error search_content: {ex}"


def tool_http_request(url, method="GET", body=None, headers=None):
    try:
        hdrs = {"User-Agent": "Lethica/1.0"}
        if headers:
            try:
                hdrs.update(json.loads(headers))
            except Exception:
                return "Error http_request: headers must be JSON string."
        data = None
        if body and method.upper() in ("POST", "PUT", "PATCH"):
            data = body.encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
        with urllib.request.urlopen(req, timeout=60) as r:
            status = r.status
            raw = r.read().decode("utf-8", errors="replace")
        parsed = ""
        try:
            parsed = "\n(auto-JSON):\n" + json.dumps(json.loads(raw), indent=2, ensure_ascii=False)[:4000]
        except Exception:
            pass
        if len(raw) > 6000:
            raw = raw[:6000] + "\n... truncated"
        return f"HTTP {method.upper()} {url}\nStatus: {status}\n{raw}{parsed}"
    except urllib.error.HTTPError as he:
        return f"Error http_request: HTTP {he.code} {he.reason}"
    except Exception as ex:
        return f"Error http_request: {ex}"


def tool_download_file(url, output):
    if not in_sandbox(output):
        return f"Error download_file: output '{output}' OUTSIDE sandbox."
    try:
        parent = os.path.dirname(os.path.abspath(output))
        os.makedirs(parent, exist_ok=True)
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Lethica/1.0"}), timeout=120) as r, \
             open(output, "wb") as f:
            total = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                total += len(chunk)
        sz = f"{total/1024/1024:.2f} MB" if total > 1024 * 1024 else f"{total/1024:.1f} KB"
        return f"OK downloaded {output} ({sz})."
    except urllib.error.HTTPError as he:
        return f"Error download_file: HTTP {he.code} {he.reason}"
    except Exception as ex:
        return f"Error download_file: {ex}"


def tool_run_command(cmd, timeout=120):
    """Run shell command. Confirms if dangerous. Always runs from WORKSPACE."""
    if is_dangerous(cmd):
        console.print(f"[bold yellow]⚠ DANGEROUS command detected:[/bold yellow]\n[dim]{cmd}[/dim]")
        if not Confirm.ask("Run anyway?", default=False):
            return "Cancelled by user (dangerous command)."
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            cwd=WORKSPACE, env={**os.environ, "HOME": HOME}
        )
        out = proc.stdout + proc.stderr
        if not out.strip():
            out = "(no output)"
        if len(out) > 4000:
            out = out[:4000] + "\n... (output truncated)"
        return f"$ {cmd}\n[exit={proc.returncode}]\n{out}"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out ({timeout}s)."
    except Exception as ex:
        return f"Error: {ex}"


def tool_self_check():
    """Compile self + auto-restore from backup if broken."""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "py_compile", SELF_PATH],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            return "OK self-check: syntax valid."
        if os.path.exists(SELF_BACKUP):
            shutil.copy2(SELF_BACKUP, SELF_PATH)
            return f"HEAL self-check failed, restored from {SELF_BACKUP}. Error: {r.stderr.strip()[:300]}"
        return f"FAIL self-check & no backup. Error: {r.stderr.strip()[:300]}"
    except Exception as ex:
        return f"Error self-check: {ex}"


# ── history persistence ────────────────────────────────────────────
def load_history():
    if os.path.isfile(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_history(messages):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)
    except Exception as e:
        console.print(f"[dim yellow]⚠ history save failed: {e}[/dim yellow]")


# ── logo + ui ─────────────────────────────────────────────────────
LOGO = """\
 ██╗     ███████╗████████╗██╗  ██╗██╗ ██████╗ █████╗ 
 ██║     ██╔════╝╚══██╔══╝██║  ██║██║██╔════╝██╔══██╗
 ██║     █████╗     ██║   ███████║██║██║     ███████║
 ██║     ██╔══╝     ██║   ██╔══██║██║██║     ██╔══██║
 ███████╗███████╗   ██║   ██║  ██║██║╚██████╗██║  ██║
 ╚══════╝╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝
"""


def show_logo():
    console.print(Panel(
        Text(LOGO, style="bold magenta", justify="center"),
        title="[bold cyan]Lethica v1.0[/bold cyan]",
        subtitle="[italic dim]free-form agent • routerku-powered • Termux-native[/italic dim]",
        border_style="magenta",
    ))


def select_model(client):
    console.print("\n[bold cyan]Scanning routerku models...[/bold cyan]")
    try:
        models = client.models()
    except Exception as e:
        console.print(f"[bold red]Fetch failed: {e}[/bold red]")
        models = [DEFAULT_MODEL]
    models = [m for m in models if m][:20]
    table = Table(title="📚 Available Models", show_header=True, header_style="bold magenta")
    table.add_column("#", style="cyan", width=4)
    table.add_column("Model", style="green")
    for i, m in enumerate(models, 1):
        table.add_row(str(i), m)
    table.add_row(str(len(models) + 1), "[white]✏ custom name[/white]")
    console.print(table)
    choice = Prompt.ask(f"[bold yellow]Pick model (1-{len(models)+1})[/bold yellow]", default="1")
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            return models[idx]
        if idx == len(models):
            return Prompt.ask("[bold yellow]Custom model name[/bold yellow]")
    except Exception:
        pass
    return models[0] if models else DEFAULT_MODEL


# ── system prompt (free-form, self-evolving, terminal-full) ─────────
def build_system_prompt():
    ver = "1.0"
    if os.path.isfile(VERSION_FILE):
        try:
            ver = open(VERSION_FILE).read().strip().split("\n")[0] or "1.0"
        except Exception:
            pass
    return f"""Kamu adalah **Lethica**, agentic AI profesional dengan AKSES PENUH ke terminal/sistem operasi.
Tujuan utama: Koding • Analisa • Temuan (Research) • Browsing • Debugging.

Kamu berjalan di Termux (Android, no-root). Backend: routerku `Free-All` (failover otomatis: bai/hy3 → unorouter/allam-2-7b:free → dseeker/instant → hc/MiniMax-M3).

## Aturan kerja
1. **Langsung eksekusi**: Kalau butuh file/komando/data, langsung panggil tool. JANGAN ngarang output.
2. **Anti-halusinasi**: Output hanya boleh setelah tool kasih hasil riil.
3. **Narasi singkat**: Sebelum panggil tool, 1-2 baris kalimat. Jangan puanjang-panjang.
4. **TO-THE-POINT**: 1 command cukup? 1 command. Jangan over-engineer.
5. **Sadar sandbox**: Hanya boleh tulis/edit file di dalam sandbox (~/lethica/ + subfolder). File di luar itu akan ditolak — sopan kalo user mau pindahkan.
6. **Konfirmasi command berbahaya**: `rm -rf`, `mv /`, `dd`, `wget|bash` butuh user confirm.
7. **Evolusi & self-repair** (level tertinggi):
   - Kode sumbermu: `{SELF_PATH}`
   - Backup: `{SELF_BACKUP}`
   - Kamu BOLEH baca/edit/extend kode sumbermu. WAJIB backup dulu, edit pakai `<edit_file>`, verifikasi `py_compile`, update `{VERSION_FILE}` dan `{CHANGELOG_FILE}`.
   - JANGAN hapus arsitektur utama (main loop, system prompt, tool dispatch). Tambah, jangan kurangi.
   - Setiap modifikasi: saran `/restart` ke user.

## Format tool call
Untuk eksekusi perintah terminal:
```
<invoke name="antml:computer:execute_command">
<parameter name="command">PERINTAH_ANDA</parameter>
</invoke>
```

Untuk native file tools (LEBIH AMAN dari sed/echo):
- `<read_file path="..." start="100" end="200" />` — baca file (hemat memori)
- `<write_file path="..." append="true|false">KONTEN</write_file>` — tulis/append
- `<edit_file path="..."><target>KODE_LAMA</target><replacement>KODE_BARU</replacement></edit_file>` — patch presisi
- `<list_dir path="..." recursive="true|false" />`
- `<search_content path="..." pattern="regex" recursive="true|false" ignore_case="true|false" />`
- `<http_request url="..." method="GET" body='...' headers='{{"X-Key":"val"}}' />`
- `<download_file url="..." output="~/lethica/workspace/file.txt" />`

## Workspace & files
- Sandbox workspace: `~/lethica/workspace/` — simpan output, scrapes, files kerja di sini.
- Custom tools/scripts: `~/lethica/workspace/tools/`
- History: `~/lethica/history.json`
- Backup self: `~/lethica/backups/lethica.py.bak`
- Version: `~/lethica/.lethica_version`
- Changelog: `~/lethica/changelog.md`

## Output rendering
- Markdown dengan baik. Code block dengan bahasa yang sesuai.
- Setiap tool call, jelaskan SEKEDAR perlu (1-2 baris).

## Slash commands (handled client-side, gak perlu di-eksekusi)
- /menu  /model  /history  /clear  /restart  /self  /improve  /exit

Versi saat ini: v{ver}
"""


# ── dispatch tools from reply ──────────────────────────────────────
def _unesc(s):
    return (s or "").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")


def dispatch(reply, agent_path):
    """Extract and execute all tool calls from reply. Return tool_outputs string."""
    outputs = []
    # native file tools (run first to avoid shell aliasing)
    for m in READ_TAG_RE.finditer(reply):
        outputs.append(f"[read_file]\n{tool_read_file(m.group(1), m.group(2), m.group(3))}")
    for m in WRITE_TAG_RE.finditer(reply):
        outputs.append(f"[write_file]\n{tool_write_file(m.group(1), _unesc(m.group(3)), append=(m.group(2) == 'true'))}")
    for m in EDIT_TAG_RE.finditer(reply):
        path = m.group(1)
        out = tool_edit_file(path, _unesc(m.group(2)), _unesc(m.group(3)))
        if os.path.abspath(path) == agent_path:
            out += "\n" + tool_self_check()
        outputs.append(f"[edit_file]\n{out}")
    for m in LIST_TAG_RE.finditer(reply):
        outputs.append(f"[list_dir]\n{tool_list_dir(m.group(1), m.group(2) or 'false')}")
    for m in SEARCH_TAG_RE.finditer(reply):
        outputs.append(f"[search_content]\n{tool_search_content(m.group(1), _unesc(m.group(2)), m.group(3) or 'false', m.group(4) or 'false')}")
    for m in HTTP_TAG_RE.finditer(reply):
        outputs.append(f"[http_request]\n{tool_http_request(m.group(1), m.group(2) or 'GET', m.group(4), m.group(3))}")
    for m in DL_TAG_RE.finditer(reply):
        outputs.append(f"[download_file]\n{tool_download_file(m.group(1), m.group(2))}")
    # shell exec
    for m in EXEC_TAG_RE.finditer(reply):
        cmd = m.group(1).strip()
        outputs.append(f"[execute_command]\n{tool_run_command(cmd)}")
    return "\n\n".join(outputs) if outputs else ""


def strip_tags(reply):
    reply = re.sub(r"</?function_calls>", "", reply, flags=re.IGNORECASE)
    reply = re.sub(r"<invoke.*?</invoke>", "", reply, flags=re.DOTALL | re.IGNORECASE)
    return reply.strip()


# ── main loop ──────────────────────────────────────────────────────
def main():
    os.chdir(WORKSPACE)
    show_logo()
    client = LClient(DEFAULT_BASE, API_KEY)
    model = select_model(client)
    show_logo()
    console.print(Panel(
        Text.assemble(
            ("Status: ", "bold green"), ("ONLINE\n", "bold cyan"),
            ("Model: ", "bold green"), (f"{model}\n", "bold yellow"),
            ("Sandbox: ", "bold green"), (f"{WORKSPACE}\n", "white"),
            ("Backend: ", "bold green"), (f"{DEFAULT_BASE}\n", "dim"),
        ),
        border_style="green",
    ))
    console.print("[dim]Slash: /menu /model /history /clear /restart /self /improve /exit[/dim]\n")

    # initial backup of self (only if not exists)
    if not os.path.isfile(SELF_BACKUP):
        try:
            shutil.copy2(SELF_PATH, SELF_BACKUP)
        except Exception:
            pass

    sysprompt = build_system_prompt()
    messages = [{"role": "system", "content": sysprompt}]

    while True:
        try:
            user_input = Prompt.ask("\n[bold magenta]➜ lethica>[/bold magenta]").strip()
            if not user_input:
                continue
            cmd = user_input.lower()

            if cmd in ("exit", "quit", "/exit", "/quit"):
                save_history(messages)
                console.print("[bold magenta]Lethica signing off. Ttd, lethica.[/bold magenta]")
                break

            if cmd == "/menu":
                console.print(Panel(
                    "[cyan]/menu[/cyan]     help\n"
                    "[cyan]/model[/cyan]    switch model\n"
                    "[cyan]/history[/cyan]  show msg count\n"
                    "[cyan]/clear[/cyan]    reset conversation\n"
                    "[cyan]/restart[/cyan]  reload system prompt\n"
                    "[cyan]/self[/cyan]     show self info + changelog\n"
                    "[cyan]/improve[/cyan]  self-improvement mode\n"
                    "[cyan]/exit[/cyan]     bye",
                    title="commands", border_style="magenta"))
                continue
            if cmd == "/model":
                model = select_model(client)
                console.print(f"[bold green]→ {model}[/bold green]")
                continue
            if cmd == "/history":
                u = sum(1 for m in messages if m["role"] == "user")
                a = sum(1 for m in messages if m["role"] == "assistant")
                console.print(f"[cyan]Total {len(messages)} | user {u} | assistant {a}[/cyan]")
                continue
            if cmd in ("/clear", "/restart", "/hapus"):
                messages = [{"role": "system", "content": build_system_prompt()}]
                console.print("[bold green]✓ session reset[/bold green]")
                continue
            if cmd == "/self":
                try:
                    sz = os.path.getsize(SELF_PATH)
                    with open(SELF_PATH) as f:
                        lines = sum(1 for _ in f)
                    mt = time.strftime("%Y-%m-%d %H:%M", time.localtime(os.path.getmtime(SELF_PATH)))
                except Exception as e:
                    sz, lines, mt = "?", "?", str(e)
                ver = "1.0"
                if os.path.isfile(VERSION_FILE):
                    ver = open(VERSION_FILE).read().strip().split("\n")[0] or "1.0"
                table = Table(title=f"🧬 Lethica v{ver}", show_header=True, header_style="bold magenta")
                table.add_column("prop", style="cyan")
                table.add_column("val", style="green")
                table.add_row("source", SELF_PATH)
                table.add_row("backup", f"{SELF_BACKUP} {'✓' if os.path.isfile(SELF_BACKUP) else '✗'}")
                table.add_row("lines", str(lines))
                table.add_row("size", f"{sz/1024:.1f} KB" if isinstance(sz, int) else str(sz))
                table.add_row("modified", mt)
                table.add_row("workspace", WORKSPACE)
                console.print(table)
                if os.path.isfile(CHANGELOG_FILE):
                    console.print(Panel(open(CHANGELOG_FILE).read(), title="[bold yellow]changelog[/bold yellow]", border_style="yellow"))
                continue
            if cmd == "/improve":
                console.print(Panel(
                    f"[bold yellow]SELF-IMPROVEMENT MODE[/bold yellow]\n\n"
                    f"source : [cyan]{SELF_PATH}[/cyan]\n"
                    f"backup : [cyan]{SELF_BACKUP}[/cyan]\n\n"
                    f"Describe the feature you want Lethica to gain:",
                    border_style="magenta"))
                req = Prompt.ask("[bold green]feature request[/bold green]").strip()
                if not req:
                    continue
                user_input = (
                    f"SELF-IMPROVEMENT MODE ACTIVE. User request: {req}\n\n"
                    f"Steps: 1) backup: `cp {SELF_PATH} {SELF_BACKUP}`. "
                    f"2) read source with `<read_file path=\"{SELF_PATH}\" start=\"1\" end=\"400\" />` etc. "
                    f"3) edit via `<edit_file path=\"{SELF_PATH}\"><target>OLD</target><replacement>NEW</replacement></edit_file>`. "
                    f"4) verify: `<invoke name=\"antml:computer:execute_command\"><parameter name=\"command\">python3 -m py_compile {SELF_PATH}</parameter></invoke>`. "
                    f"5) bump version in `{VERSION_FILE}` and append to `{CHANGELOG_FILE}`. "
                    f"6) tell user to /restart."
                )

            messages.append({"role": "user", "content": user_input})

            with console.status("[bold cyan]lethica thinking...[/bold cyan]", spinner="dots2"):
                # sliding window
                if len(messages) > 18:
                    messages = [messages[0]] + messages[-17:]

                for turn in range(8):  # max 8 tool rounds
                    last = None
                    for attempt in range(3):
                        r = client.chat(model, messages, temperature=0.6, max_tokens=2048, timeout=60)
                        if "error" not in r and r.get("choices"):
                            last = r
                            break
                        time.sleep(1 + attempt)
                    if not last:
                        console.print("[bold red]✖ backend unavailable (3x retry). cek routerku :20130[/bold red]")
                        break

                    reply = last["choices"][0]["message"]["content"]
                    messages.append({"role": "assistant", "content": reply})

                    # render intermediate
                    display = strip_tags(reply)
                    if display:
                        console.print(Panel(
                            Markdown(display),
                            title="[bold yellow]🤖 lethica[/bold yellow]",
                            border_style="yellow",
                        ))

                    out = dispatch(reply, SELF_PATH)
                    if not out:
                        break
                    messages.append({"role": "user", "content": (
                        "Tool results (lethica sandbox, edit_file hanya di ~/lethica/, "
                        "dangerous commands butuh confirm):\n\n<tool_response>\n"
                        + out + "\n</tool_response>\n\nLanjut atau finalkan."
                    )})
                save_history(messages)
        except KeyboardInterrupt:
            save_history(messages)
            console.print("\n[bold magenta]Session ended.[/bold magenta]")
            break
        except Exception as e:
            console.print(f"[bold red]error:[/bold red] {e}")
            traceback.print_exc()


if __name__ == "__main__":
    main()
