# core/tools_io.py — v3.7.2 Lethica tools: filesystem / sandbox / command / self-heal.
# Split dari tools.py. Tidak memakai tool_* dari tools_net/tools_mem (kecuali
# _curl_request untuk http fallback — diimpor dari tools_net).
import os
import re
import json
import time
import shutil
import subprocess
import urllib.request
import urllib.error
import urllib.parse

from core import config, stats, cache
from core.tools_net import _HAVE_CURL  # noqa: E402  (shared curl availability flag)

console = None  # injected


def in_sandbox(path):
    """True kalau path di dalam allowed dirs. Resolve traversal & symlinks."""
    if not path or not isinstance(path, str):
        return False
    path = os.path.expanduser(os.path.expandvars(path))
    try:
        p = os.path.realpath(path)
    except Exception:
        return False
    if p in ("/", os.path.expanduser("~"), ""):
        return False
    try:
        core_files = ({os.path.join(config.CORE_DIR, f) for f in os.listdir(config.CORE_DIR)}
                      if os.path.isdir(config.CORE_DIR) else set())
    except OSError:
        core_files = set()
    if p == config.SELF_PATH or p in core_files:
        return True
    for d in config.SANDBOX_DIRS:
        if not d or not isinstance(d, str):
            continue
        d_real = os.path.realpath(d) if os.path.exists(d) else None
        if not d_real:
            continue
        if p == d_real or p.startswith(d_real.rstrip("/") + "/"):
            return True
    return False


def is_dangerous(cmd):
    if not cmd or not isinstance(cmd, str):
        return False
    return bool(DANGER_RE.search(cmd))


def _expand(path):
    """v2.9.5: expand ~ / $VAR + realpath. Model sering nulis '~/lethica/...' — dulu
    tool_read_file/list_dir langsung os.path.isfile('~/...') → selalu not found."""
    if not path:
        return path
    p = os.path.expanduser(os.path.expandvars(str(path)))
    try:
        return os.path.realpath(p)
    except Exception:
        return p


DANGER_RE = re.compile(
    r"(?:"
    r"rm\s+-r[fF]|rm\s+-fr|rm\s+-rf|rm\s+--recursive\s+--force|"
    r"rm\s+-r[^-]|rm\s+-R[^-]|rm\s+--recursive\b|"  # v2.9.6: rm -r / rm -R tanpa -f juga destructive
    r":\(\)\s*\{\s*:|:&\s*\};:"
    r"|mkfs(?:\.[a-z0-9]+)?\s"
    r"|(?<![a-zA-Z0-9_/])mv\s+/"
    r"|(?<![a-z0-9_/])dd\s+if="
    r"|(?<![a-z0-9_/])wget\s"
    r">\s*/dev/(?:sd|hd|nvme|mmcblk)"
    r"|chmod\s+-R\s+777"
    r"|curl\s+[^|]+\|\s*(?:sh|bash)\b"
    r")",
    re.IGNORECASE,
)


def tool_read_file(path, start=None, end=None):
    path = _expand(path)
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
    path = _expand(path)
    if not in_sandbox(path):
        msg = (f"Error write_file: path '{path}' is OUTSIDE sandbox. Allowed: "
               f"{[os.path.realpath(d) for d in config.SANDBOX_DIRS if os.path.exists(d)]}. "
               f"Use a path inside ~/lethica/.")
        if console:
            console.print(f"[bold yellow]⚠ {msg}[/bold yellow]")
        return msg
    try:
        parent = os.path.dirname(os.path.abspath(path))
        os.makedirs(parent, exist_ok=True)
        mode = "a" if append else "w"
        with open(path, mode, encoding="utf-8") as f:
            f.write(content or "")
        verb = "appended to" if append else "wrote to"
        return f"OK {verb} {path} ({len(content or '')} chars)."
    except Exception as ex:
        return f"Error write_file: {ex}"


def tool_edit_file(path, target, replacement):
    path = _expand(path)
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
    path = _expand(path)
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
                    out.append("  ?")
        if len(entries) > 200:
            out.append(f"  ... +{len(entries) - 200} more")
        return "\n".join(out)
    except Exception as ex:
        return f"Error list_dir: {ex}"


def tool_search_content(path, pattern, recursive="false", ignore_case="false"):
    path = _expand(path)
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
        hdrs = {"User-Agent": f"Lethica/{config.VERSION}"}
        if headers:
            try:
                hdrs.update(json.loads(headers))
            except Exception:
                return "Error http_request: headers must be JSON string."
        data = None
        if body and method.upper() in ("POST", "PUT", "PATCH"):
            data = body.encode("utf-8")
            hdrs.setdefault("Content-Type", "application/json")
        status = raw = None
        if _HAVE_CURL:
            try:
                from core.tools_net import _curl_request
                status, _fu, raw, _h, _c = _curl_request(url, method.upper(), hdrs, data, config.HTTP_TIMEOUT)
            except Exception:
                status = raw = None
        if status is None:
            req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
            with urllib.request.urlopen(req, timeout=config.HTTP_TIMEOUT) as r:
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
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": f"Lethica/{config.VERSION}"}), timeout=120) as r, \
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


def _scope_violation(cmd):
    """v3.2: tolak command yang sengaja keluar dari workspace (cd ../../dst,
    atau path absolut di luar WORKSPACE/HOME/tmp). Read-only (ls/cat/find) tetap diizinkan."""
    import shlex as _sl
    _td = getattr(config, "TASK_DIR", None)
    ROOTS = ([os.path.realpath(_td)] if _td else [os.path.realpath(config.WORKSPACE)])
    ROOTS += ["/tmp", os.path.realpath("/data/data/com.termux/files/usr/tmp")]
    if not _td:
        ROOTS.append(os.path.realpath(config.WORKSPACE))
    def outside(p):
        try:
            rp = os.path.realpath(os.path.expanduser(p))
        except Exception:
            return False
        return not any(rp == r or rp.startswith(r + os.sep) for r in ROOTS)
    # 1) explicit cd
    for m in re.finditer(r"\bcd\s+(?:-[LP]?\s+)?(?!-)([^;&|\n]+)", cmd):
        t = m.group(1).strip().strip("\"'")
        if t and outside(t):
            return t
    # 2) rm/touch/mkdir/nohup/redirect ke path luar
    for m in re.finditer(r"(?:\brm\b|\btouch\b|\bmkdir\b|\bnohup\b|>\s*)(?:\s+-[\w-]+)*\s+([^\s;&|]+)", cmd):
        t = m.group(1).strip().strip("\"'")
        if t.startswith(("/", "~", "..")) and outside(t):
            return t
    # 3) python3/nohup menjalankan script di luar workspace
    for m in re.finditer(r"\b(?:python3?|bash|sh)\s+([^\\s;&|]+\.py)", cmd):
        t = m.group(1).strip().strip("\"'")
        if t.startswith(("/", "~", "..")) and outside(t):
            return t
    return None


def tool_run_command(cmd, timeout=120):
    """Run shell command. Confirms if dangerous. Always runs from WORKSPACE."""
    # v3.2: scope guard — jangan izinkan agent menyentuh path di luar workspace.
    _bad = _scope_violation(cmd)
    if _bad:
        return (f"BLOCKED (scope): target di luar workspace task → {_bad}\n"
                f"Workspace task: {config.WORKSPACE}\n"
                f"Command tidak dijalankan. Gunakan path di dalam workspace.")
    if config.DANGER_CONFIRM and is_dangerous(cmd):
        if console:
            console.print(f"[bold yellow]⚠ DANGEROUS command detected:[/bold yellow]\n[dim]{cmd}[/dim]")
            from rich.prompt import Confirm
            ok = Confirm.ask("Run anyway?", default=False)
        else:
            ok = False
        if not ok:
            return "Cancelled by user (dangerous command)."
    try:
        proc = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            cwd=config.WORKSPACE, env={**os.environ, "HOME": config.HOME}
        )
        out = proc.stdout + proc.stderr
        if not out.strip():
            out = "(no output)"
        if len(out) > 16000:
            out = out[:16000] + "\n... (output truncated at 16000 chars)"
        return f"$ {cmd}\n[exit={proc.returncode}]\n{out}"
    except subprocess.TimeoutExpired:
        return f"Error: command timed out ({timeout}s)."
    except Exception as ex:
        return f"Error: {ex}"


# ── self-heal / backup ──────────────────────────────────────────────
def _newest_backup(base):
    """v2.9.3 fix: pilih backup by MTIME, bukan nama."""
    import glob
    exact = os.path.join(config.BACKUP_DIR, base + ".bak")
    if os.path.isfile(exact):
        return exact
    cands = [c for c in glob.glob(os.path.join(config.BACKUP_DIR, base + "*"))
             if os.path.isfile(c) and not c.endswith((".tar.gz", ".md"))]
    if not cands:
        return None
    return max(cands, key=lambda c: os.path.getmtime(c))


def tool_self_check():
    """Compile self + auto-restore from backup if broken."""
    try:
        r = subprocess.run(
            ["python3", "-m", "py_compile", config.SELF_PATH],
            capture_output=True, text=True
        )
        if r.returncode == 0:
            return "OK self-check: syntax valid."
        bak = _newest_backup(os.path.basename(config.SELF_PATH))
        if bak:
            shutil.copy2(bak, config.SELF_PATH)
            return f"HEAL self-check failed, restored from {os.path.basename(bak)}. Error: {r.stderr.strip()[:300]}"
        return f"FAIL self-check & no backup. Error: {r.stderr.strip()[:300]}"
    except Exception as ex:
        return f"Error self-check: {ex}"


def _py_compile_targets():
    """Return list abs path semua file sumber yang harus compile-clean."""
    import glob
    targets = [config.SELF_PATH]
    if os.path.isdir(config.CORE_DIR):
        targets += sorted(glob.glob(os.path.join(config.CORE_DIR, "*.py")))
    return [t for t in targets if os.path.isfile(t)]


def verify_self():
    """Compile-check SELF_PATH + seluruh core/*.py. Return (all_ok, [failed_files])."""
    import py_compile
    failed = []
    for t in _py_compile_targets():
        try:
            py_compile.compile(t, doraise=True)
        except Exception:
            failed.append(t)
    return (len(failed) == 0), failed


def self_heal_rollback():
    """Mode 2 safeguard: kalau compile gagal, restore SELF_PATH + core dari backup otomatis.
    Return (restored, message)."""
    ok, failed = verify_self()
    if ok:
        return False, "✓ all targets compile-clean, no rollback needed"
    restored, missing = [], []
    for f in failed:
        base = os.path.basename(f)
        c = _newest_backup(base)
        if not c:
            missing.append(base)
            continue
        try:
            shutil.copy(c, f)
            restored.append(f"{base} <- {os.path.basename(c)}")
        except Exception:
            missing.append(base)
    ok2, still = verify_self()
    note = f" | tanpa backup: {', '.join(missing)}" if missing else ""
    if ok2:
        return True, "✓ rollback berhasil: " + (", ".join(restored) or "(nothing restored)") + note
    return True, f"⚠ rollback GAGAL — masih broken: {still}{note} (restored: {', '.join(restored) or 'none'})"


def backup_self():
    """v2.5: rolling backup last-known-good — simpan SEBELUM edit, replace existing."""
    try:
        os.makedirs(config.BACKUP_DIR, exist_ok=True)
        bak = os.path.join(config.BACKUP_DIR, os.path.basename(config.SELF_PATH) + ".bak")
        shutil.copy2(config.SELF_PATH, bak)
        if os.path.isdir(config.CORE_DIR):
            for f in sorted(os.listdir(config.CORE_DIR)):
                if f.endswith(".py"):
                    try:
                        shutil.copy2(os.path.join(config.CORE_DIR, f),
                                     os.path.join(config.BACKUP_DIR, f + ".bak"))
                    except OSError:
                        continue
        return bak
    except Exception:
        return None
