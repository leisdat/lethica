# core/tools.py — sandbox check, danger detect, semua tool_* functions
import os
import re
import json
import time
import shutil
import base64
import subprocess
import urllib.request
import urllib.error
import urllib.parse

# v2.9.1 HTTP stack: curl_cffi browser impersonation (TLS/JA3 fingerprint).
try:
    from curl_cffi import requests as _curl
    _HAVE_CURL = True
except Exception:
    _curl = None
    _HAVE_CURL = False

def _curl_request(url, method="GET", headers=None, data=None, timeout=30, impersonate="chrome"):
    """Browser-impersonating HTTP. Return (status, final_url, text, headers, cookies). Raise on fail."""
    s = _curl.Session(impersonate=impersonate)
    r = s.request(method=method.upper(), url=url, headers=headers or {}, data=data,
                  timeout=timeout, allow_redirects=True)
    try:
        cookies = dict(r.cookies)
    except Exception:
        cookies = {}
    return r.status_code, str(r.url), r.text, r.headers, cookies

from core import config, stats, cache

console = None  # injected

# convenience alias (tags.py memakai *_TAG_RE spesifik; ini untuk kompat)
TAG_RE = None

EXEC_TAG_RE = re.compile(
    r'<exec\s+command="([^"]*)"(?:\s+timeout="(\d+)")?\s*/?>'
    r'|<invoke\s+name="antml:computer:execute_command">\s*<parameter\s+name="command">(.*?)</parameter>\s*</invoke>',
    re.DOTALL | re.IGNORECASE,
)
READ_TAG_RE = re.compile(
    r'<read_file\s+path="([^"]+)"(?:\s+start="(\d+)")?(?:\s+end="(\d+)")?\s*/?>',
    re.IGNORECASE,
)
WRITE_TAG_RE = re.compile(
    r'<write_file\s+path="([^"]+)"(?:\s+append="(true|false)")?\s*>(.*?)</write_file>'
    r'|<write_file\s+path="([^"]+)"(?:\s+append="(true|false)")?\s+content="([^"]*)"\s*/?>',
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
MEMORY_TAG_RE = re.compile(r'<memory\s+([^>]*?)/?>', re.IGNORECASE)
PLAN_TAG_RE = re.compile(r'<plan\s+([^>]*?)/?>', re.IGNORECASE)
SPAWN_TAG_RE = re.compile(r'<spawn\s+([^>]*?)/?>', re.IGNORECASE)
WEBSEARCH_TAG_RE = re.compile(r'<web_search\s+([^>]*?)/?>', re.IGNORECASE)
BROWSE_TAG_RE = re.compile(r'<browse\s+([^>]*?)/?>', re.IGNORECASE)
SKILL_TAG_RE = re.compile(r'<skill\s+([^>]*?)/?>', re.IGNORECASE)
RUNCODE_TAG_RE = re.compile(
    r'<run_code\s+lang="([^"]+)"(?:\s+timeout="(\d+)")?>\s*(.*?)\s*</run_code>',
    re.DOTALL | re.IGNORECASE,
)

DANGER_RE = re.compile(
    r"(?:"
    r"rm\s+-r[fF]|rm\s+-fr|rm\s+-rf|rm\s+--recursive\s+--force|"
    r"rm\s+-r[^-]|rm\s+-R[^-]|rm\s+--recursive\b|"  # v2.9.6: rm -r / rm -R tanpa -f juga destructive
    r":\(\)\s*\{\s*:|:&\s*\};:"
    r"|mkfs(?:\\.[a-z0-9]+)?\s"
    r"|(?<![a-zA-Z0-9_/])mv\s+/"
    r"|(?<![a-z0-9_/])dd\s+if="
    r"|(?<![a-z0-9_/])wget\s"
    r">\s*/dev/(?:sd|hd|nvme|mmcblk)"
    r"|chmod\s+-R\s+777"
    r"|curl\s+[^|]+\|\s*(?:sh|bash)\b"
    r")",
    re.IGNORECASE,
)


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
    """v2.9.5: expand ~ / $VAR + realpath. Model sering nulis '~/lethica/...' —
    dulu tool_read_file/list_dir langsung os.path.isfile('~/...') → selalu not found.
    v2.9.6 FIX: realpath setelah expand — blok path traversal '../' yang lolos sandbox
    (workspace/../.bashrc ke-realpath jadi ~/.bashrc tapi dicek sebelum di-resolve)."""
    if not path:
        return path
    p = os.path.expanduser(os.path.expandvars(str(path)))
    try:
        return os.path.realpath(p)
    except Exception:
        return p


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
        msg = f"Error write_file: path '{path}' is OUTSIDE sandbox. Allowed: {[os.path.realpath(d) for d in config.SANDBOX_DIRS if os.path.exists(d)]}. Use a path inside ~/lethica/."
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
    atau path absolut di luar WORKSPACE/HOME/tmp). Kasus nyata: agent repair
    nyasar `cd ~/lethica/workspace/atria/auto_reg && rm -f ...` — project
    orang lain, bukan task-nya. Read-only (ls/cat/find) tetap diizinkan."""
    import shlex as _sl
    _td = getattr(config, "TASK_DIR", None)
    # KETAT: kalau task punya TASK_DIR, HANYA itu (+/tmp). WORKSPACE global
    # TIDAK ikut — kalau tidak, workspace/<project-lain> tetap lolos (bug nyata:
    # repair agent nyasar ke workspace/atria/auto_reg milik project lain).
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
    for m in re.finditer(r"\b(?:python3?|bash|sh)\s+([^\s;&|]+\.py)", cmd):
        t = m.group(1).strip().strip("\"'")
        if t.startswith(("/", "~", "..")) and outside(t):
            return t
    return None


def tool_run_command(cmd, timeout=120):
    """Run shell command. Confirms if dangerous. Always runs from WORKSPACE."""
    # v3.2: scope guard — jangan izinkan agent menyentuh path di luar workspace.
    _bad = _scope_violation(cmd)
    if _bad:
        _log = None
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


def _newest_backup(base):
    """v2.9.3 fix: pilih backup by MTIME, bukan nama.
    Dulu `sorted(...)[-1]` → 'lethica.py.bak-v2.4.1' menang atas 'lethica.py.bak'
    (karena '-' > ''), jadi self-check gagal = restore monolit v2.4.1 83KB
    nimpa entry point 2KB. Prefer <base>.bak (rolling last-known-good dari
    backup_self), fallback ke kandidat termuda by mtime."""
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
    """v2.5: rolling backup last-known-good — simpan SEBELUM edit, replace existing.
    v2.9.3 fix: dulu HANYA SELF_PATH yang di-backup → 5 modul core (tokens, cache,
    rag, stats, __init__) gak punya kandidat sama sekali, jadi self_heal_rollback
    mustahil buat mereka. Sekarang snapshot SELF_PATH + seluruh core/*.py.
    Return path backup utama (atau None)."""
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


# ── web search / browse ─────────────────────────────────────────────
SEARCH_UA = "Mozilla/5.0 (Linux; Android 13; Redmi Note 11) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Mobile Safari/537.36"


def _fetch(url, timeout=20):
    """GET URL → text. Raise kalau gagal (caller yang handle)."""
    hdrs = {"User-Agent": SEARCH_UA, "Accept-Language": "en-US,en;q=0.9"}
    if _HAVE_CURL:
        try:
            return _curl_request(url, "GET", hdrs, None, timeout)[2]
        except Exception:
            pass
    req = urllib.request.Request(url, headers=hdrs)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _strip_html(s):
    return re.sub(r"<[^>]+>", "", s).strip()


def _decode_bing_redirect(url):
    """bing.com/ck/a redirect → URL asli (base64url di param u=a1)."""
    if "bing.com/ck/a" not in url:
        return url
    um = re.search(r"[?&]u=a1([^&]+)", url)
    if not um:
        return url
    try:
        tok = um.group(1).replace("-", "+").replace("_", "/")
        tok += "=" * (-len(tok) % 4)
        dec = base64.b64decode(tok).decode("utf-8", errors="replace")
        if dec.startswith("http"):
            return dec
    except Exception:
        pass
    return url


def _search_bing(query, limit):
    """Parse hasil Bing. Return list [{title,url,snippet}] — raise kalau fetch gagal."""
    bp = _fetch(f"https://www.bing.com/search?q={urllib.parse.quote(query)}&count={limit+5}")
    results = []
    for c in re.split(r'<li class="b_algo"', bp)[1:]:
        h2 = (re.search(r'<a[^>]*href="(http[^"]+)"[^>]*>\s*<h2[^>]*>(.*?)</h2>', c[:3000], re.DOTALL)
              or re.search(r'<h2[^>]*>\s*<a[^>]*href="(http[^"]+)"[^>]*>(.*?)</a>', c[:3000], re.DOTALL))
        if not h2:
            continue
        url = _decode_bing_redirect(h2.group(1))
        title = _strip_html(h2.group(2))
        snm = re.search(r"<p[^>]*>(.*?)</p>", c, re.DOTALL)
        snippet = _strip_html(snm.group(1))[:200] if snm else ""
        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


def _search_ddg(query, limit):
    """Parse hasil DDG lite. Return list [{title,url,snippet}] — raise kalau fetch gagal."""
    page = _fetch(f"https://lite.duckduckgo.com/lite/?q={urllib.parse.quote(query)}")
    results = []
    for m in re.finditer(
        r"<a[^>]*?href=['\"](https?://[^'\"]+)['\"][^>]*?class=['\"]result-link['\"][^>]*>(.*?)</a>(.*?)(?=<a[^>]*class=['\"]result-link|\Z)",
        page, re.DOTALL,
    ):
        title = _strip_html(m.group(2))
        url = m.group(1)
        if "duckduckgo.com" in url and "/l/?" in url:
            mm = re.search(r"uddg=([^&]+)", url)
            if mm:
                url = urllib.parse.unquote(mm.group(1))
        snm = re.search(r"class=['\"]result-snippet['\"]>(.*?)</td>", m.group(3), re.DOTALL)
        snippet = _strip_html(snm.group(1))[:200] if snm else ""
        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


def _search_searx(query, limit):
    """SearXNG public instance scrape. Return list [{title,url,snippet}] — raise kalau gagal."""
    import random
    instances = [
        "https://searx.be", "https://search.brave4u.com", "https://search.inetol.net",
        "https://priv.au", "https://baresearch.org", "https://searx.work",
    ]
    inst = random.choice(instances)
    page = _fetch(f"{inst}/search?q={urllib.parse.quote(query)}&format=json", timeout=15)
    try:
        data = json.loads(page)
        results = []
        for r in data.get("results", [])[:limit]:
            url = r.get("url")
            if url and url.startswith("http"):
                results.append({
                    "title": _strip_html(r.get("title", "")) or url,
                    "url": url,
                    "snippet": _strip_html(r.get("content", ""))[:200],
                })
            if len(results) >= limit:
                break
        return results
    except Exception:
        return []


def _search_google_scrape(query, limit):
    """Google scrape via lite endpoint. Return list — raise kalau gagal."""
    page = _fetch(f"https://www.google.com/search?q={urllib.parse.quote(query)}&num={limit+5}", timeout=15)
    results = []
    for m in re.finditer(r'<a href=\"(https?://[^\"]+)\"[^>]*><h3[^>]*>(.*?)</h3>', page, re.DOTALL):
        url = m.group(1)
        if "google" in url or "webcache" in url:
            continue
        title = _strip_html(m.group(2))
        snm = re.search(r'<div[^>]*class=\"[^"]*BNeawe[^"]*\"[^>]*>(.*?)</div>', m.group(0), re.DOTALL)
        snippet = _strip_html(snm.group(1))[:200] if snm else ""
        if title and url.startswith("http"):
            results.append({"title": title, "url": url, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


def _with_retry(fn, max_attempts=2, base_delay=1.5):
    """Retry fn() dengan exponential backoff. Return list atau raise attempt terakhir."""
    last = None
    for i in range(max_attempts):
        try:
            r = fn()
            if r:
                return r
        except Exception as ex:
            last = ex
        if i < max_attempts - 1:
            time.sleep(base_delay * (2 ** i))
    if last:
        raise last
    return []


def tool_web_search(query, limit=None):
    """Search via chain: Bing → DDG lite → SearXNG → Google scrape. Zero-dep urllib, retry+backoff. Cache 30m (v2.8.6)."""
    limit = max(1, min(int(limit or config.SEARCH_LIMIT), 10))
    ck = f"search:{urllib.parse.quote(query)}:{limit}"
    cached = cache.get(ck, ttl=1800)
    if cached is not None:
        return cached + "\n(cached 30m)"
    errors = []
    for name, fn in (("bing", lambda: _search_bing(query, limit)),
                     ("ddg", lambda: _search_ddg(query, limit)),
                     ("searx", lambda: _search_searx(query, limit)),
                     ("google", lambda: _search_google_scrape(query, limit))):
        try:
            results = _with_retry(fn)
            if results:
                out = json.dumps(results[:limit], ensure_ascii=False, indent=1)
                cache.put(ck, out, ttl=1800)
                return out
        except Exception as ex:
            errors.append(f"{name}: {ex}")
    return f"Error web_search: semua engine gagal ({' | '.join(errors)})"


BROWSER_COOKIE_JAR = {}  # domain -> {cookie: val}
BROWSER_LAST_URL = [None]


def _browser_headers(domain, extra=None):
    h = {"User-Agent": SEARCH_UA, "Accept": "text/html,*/*", "Accept-Language": "en-US,en;q=0.9"}
    if domain in BROWSER_COOKIE_JAR:
        h["Cookie"] = "; ".join(f"{k}={v}" for k, v in BROWSER_COOKIE_JAR[domain].items())
    if extra:
        try:
            h.update(json.loads(extra) if isinstance(extra, str) else extra)
        except Exception:
            pass
    return h


def _browser_store_cookies(resp, domain):
    # v2.5 fix: setdefault dulu — deletion cookie gak KeyError lagi
    try:
        jar = BROWSER_COOKIE_JAR.setdefault(domain, {})
        for hv in resp.headers.get_all("Set-Cookie") or []:
            part = hv.split(";")[0]
            if "=" in part:
                k, v = part.split("=", 1)
                if v.strip().lower() in ("", "deleted"):
                    jar.pop(k, None)
                else:
                    jar[k] = v
    except Exception:
        pass


def _browser_store_cookies_curl(cookies, domain):
    """Simpan cookies dari curl_cffi response (dict) ke jar manual."""
    try:
        jar = BROWSER_COOKIE_JAR.setdefault(domain, {})
        for k, v in (cookies or {}).items():
            if str(v).strip().lower() in ("", "deleted"):
                jar.pop(k, None)
            else:
                jar[k] = v
    except Exception:
        pass


def tool_browse(url, data=None, method="GET"):
    """Browser session dengan cookie jar persist. GET buka page, POST kirim form/login."""
    if not url or not isinstance(url, str):
        return "Error browse: url required (contoh: <browse url=\"https://...\" /> atau tanpa url untuk reload last)."
    if not url.startswith(("http://", "https://")):
        return f"Error browse: invalid url '{url}' (butuh http/https)."
    url = url.replace("\\\"", "\"")
    method = (method or "GET").upper()
    # v2.8: cache GET browse 10 menit (POST gak di-cache — form/login)
    bck = None
    if method == "GET":
        bck = f"browse:{url}"
        bcached = cache.get(bck, ttl=600)
        if bcached is not None:
            return bcached + "\n(cached 10m)"
    if not url.startswith("http") and BROWSER_LAST_URL[0]:
        url = urllib.parse.urljoin(BROWSER_LAST_URL[0], url)
    domain = urllib.parse.urlparse(url).netloc
    try:
        hdrs = _browser_headers(domain)
        body = None
        if data:
            data = data.replace("\\\"", "\"")
            body = data.encode("utf-8")
            hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")
        status = final_url = raw = None
        if _HAVE_CURL:
            try:
                status, final_url, raw, _ch, _cc = _curl_request(url, method, hdrs, body, 30)
                _browser_store_cookies_curl(_cc, domain)
            except Exception:
                status = final_url = raw = None
        if status is None:
            req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
            with urllib.request.urlopen(req, timeout=30) as r:
                status = r.status
                final_url = r.geturl()
                raw = r.read().decode("utf-8", errors="replace")
                _browser_store_cookies(r, domain)
        BROWSER_LAST_URL[0] = final_url
        body_m = re.search(r"<body[^>]*>(.*)</body>", raw, re.DOTALL | re.IGNORECASE)
        page = body_m.group(1) if body_m else raw
        page = re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", "", page, flags=re.DOTALL | re.IGNORECASE)
        links = []
        for lm in re.finditer(r'<a[^>]*href="([^"#]+)"[^>]*>(.*?)</a>', page, re.DOTALL):
            txt = re.sub(r"<[^>]+>", "", lm.group(2)).strip()[:80]
            if txt:
                links.append(f"  {lm.group(1)[:120]}  → {txt}")
            if len(links) >= 30:
                break
        text = re.sub(r"<br\s*/?>", "\n", page, flags=re.IGNORECASE)
        text = re.sub(r"</(?:p|div|tr|li|h[1-6])>", "\n", text, flags=re.IGNORECASE)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n", text).strip()
        if len(text) > 4000:
            text = text[:4000] + "\n... (truncated)"
        out = f"HTTP {method} {url} → {status} (final: {final_url})\nCookies: {len(BROWSER_COOKIE_JAR.get(domain, {}))} stored\n\n=== PAGE TEXT ===\n{text}"
        if links:
            out += "\n\n=== LINKS ===\n" + "\n".join(links)
        if bck:
            cache.put(bck, out, ttl=600)
        return out
    except urllib.error.HTTPError as he:
        return f"Error browse: HTTP {he.code} {he.reason} on {url}"
    except Exception as ex:
        return f"Error browse: {ex}"


# ── memory bank / plan ──────────────────────────────────────────────
def _memory_file(key):
    safe = re.sub(r"[^a-zA-Z0-9_\-]", "_", key or "").strip("_")[:80] or "untitled"
    return os.path.join(config.MEMORY_DIR, safe + ".md")


def tool_memory(action, key=None, content=None):
    """Memory bank: save/load/search/forget. Files di ~/lethica/memory/."""
    action = (action or "load").lower()
    if action == "save":
        if not key or content is None:
            return "Error memory save: butuh key dan content."
        content = content.replace("\\n", "\n").replace("\\\"", "\"")
        path = _memory_file(key)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# {key}\n{content}\n")
        return f"OK memory saved: {path}"
    if action == "load":
        if key:
            path = _memory_file(key)
            if not os.path.isfile(path):
                return f"Error memory load: '{key}' not found. Available: {', '.join(sorted(f[:-3] for f in os.listdir(config.MEMORY_DIR) if f.endswith('.md'))) or '(empty)'}"
            with open(path, encoding="utf-8") as f:
                return f.read()[:4000]
        entries = sorted(f[:-3] for f in os.listdir(config.MEMORY_DIR) if f.endswith(".md"))
        return "Memory entries:\n" + ("\n".join(f"  - {e}" for e in entries) or "(empty)")
    if action == "search":
        if not key:
            return "Error memory search: butuh key (pattern regex)."
        try:
            rx = re.compile(key, re.IGNORECASE)
        except re.error as rex:
            return f"Error memory search: bad regex - {rex}"
        hits = []
        for fn in os.listdir(config.MEMORY_DIR):
            if not fn.endswith(".md"):
                continue
            fp = os.path.join(config.MEMORY_DIR, fn)
            try:
                with open(fp, encoding="utf-8", errors="replace") as f:
                    for i, line in enumerate(f, 1):
                        if rx.search(line):
                            hits.append(f"{fn[:-3]}:{i}: {line.rstrip()[:150]}")
                            if len(hits) >= 30:
                                break
            except OSError:
                continue
            if len(hits) >= 30:
                break
        return "\n".join(hits) or f"No matches for '{key}' in memory."
    if action == "forget":
        path = _memory_file(key)
        if os.path.isfile(path):
            os.remove(path)
            return f"OK memory forgotten: {key}"
        return f"Error memory forget: '{key}' not found."
    return f"Error memory: unknown action '{action}' (save/load/search/forget)."


def memory_bank_summary():
    try:
        entries = sorted(f[:-3] for f in os.listdir(config.MEMORY_DIR) if f.endswith(".md"))
        if not entries:
            return ""
        return "\n".join(f"- {e}" for e in entries[:40])
    except Exception:
        return ""


def plan_file():
    return os.path.join(config.PLAN_DIR, "active-plan.md")


def tool_plan(action, content=None):
    """Plan mode: save / append / show / clear."""
    action = (action or "show").lower()
    pf = plan_file()
    if action == "save":
        if not content:
            return "Error plan save: butuh content."
        content = content.replace("\\n", "\n")
        with open(pf, "w", encoding="utf-8") as f:
            f.write(f"# Active Plan\n{content}\n")
        return f"OK plan saved: {pf}"
    if action == "append":
        if not content:
            return "Error plan append: butuh content."
        with open(pf, "a", encoding="utf-8") as f:
            f.write(content.replace("\\n", "\n") + "\n")
        return "OK plan appended."
    if action == "show":
        if not os.path.isfile(pf):
            return "(no active plan)"
        with open(pf, encoding="utf-8") as f:
            return f.read()[:3000]
    if action == "clear":
        if os.path.isfile(pf):
            os.remove(pf)
            return "OK plan cleared."
        return "(no active plan)"
    return f"Error plan: unknown action '{action}'."


def _parse_spawn_tasks(raw):
    """Parse arg tasks → list [{"name","task"}].
    Format 1 (JSON): [{"name":"riset-a","task":"..."}, ...] atau {"tasks":[...]}
    Format 2 (baris):  nama: task  /  nama | task  (satu subtask per baris)"""
    import json as _json
    t = (raw or "").strip()
    if not t:
        return []
    if t.startswith(("[", "{")):
        try:
            d = _json.loads(t)
            if isinstance(d, dict):
                d = d.get("tasks") or []
            out = []
            for i, it in enumerate(d):
                if isinstance(it, dict) and it.get("task"):
                    out.append({"name": str(it.get("name") or f"agent-{i+1}"),
                                "task": str(it["task"])})
                elif isinstance(it, str) and it.strip():
                    out.append({"name": f"agent-{i+1}", "task": it.strip()})
            return out
        except Exception:
            pass  # jatuh ke format baris
    out = []
    for i, line in enumerate(t.splitlines()):
        line = line.strip().strip("-*• ").strip()
        if not line:
            continue
        if ":" in line:
            name, task = line.split(":", 1)
        elif "|" in line:
            name, task = line.split("|", 1)
        else:
            name, task = f"agent-{i+1}", line
        name, task = name.strip()[:40] or f"agent-{i+1}", task.strip()
        if task:
            out.append({"name": name, "task": task})
    return out


def tool_spawn(tasks=None, max_rounds=None):
    """Sub-agent paralel: delegasikan subtask independen ke N agent mini."""
    from core import subagents  # lazy: hindari circular import
    if subagents.in_subagent():
        return "[spawn] ERROR: sub-agent tidak boleh spawn lagi (max depth 1)."
    parsed = _parse_spawn_tasks(tasks)
    if not parsed:
        return ("[spawn] ERROR: arg 'tasks' kosong/tidak ke-parse. Format: "
                "JSON [{\"name\":\"a\",\"task\":\"...\"}] atau baris 'nama: task'.")
    try:
        mr = int(max_rounds) if max_rounds else None
    except (TypeError, ValueError):
        mr = None
    return subagents.spawn(parsed, max_rounds=mr)


# ── v2.9: skill loader (Hermes skills di ~/lethica/skills/) ──
SKILL_DIR = os.path.join(config.LETHICA_DIR, "skills")
# index nama->path di-build sekali
_SKILL_INDEX = {}   # key: "layer/skill" (relative path) -> abs path SKILL.md
_SKILL_ALIAS = {}   # basename -> [ "layer/skill", ... ]  (collision disambiguation)


def _build_skill_index():
    """Index semua SKILL.md secara rekursif.
    Key = relative path (layer/skill) supaya tidak ada collision antar layer.
    _SKILL_ALIAS menyimpan pemetaan basename -> [relkey] untuk resolve ambigu.
    """
    global _SKILL_INDEX, _SKILL_ALIAS
    _SKILL_INDEX = {}
    _SKILL_ALIAS = {}
    if not os.path.isdir(SKILL_DIR):
        return _SKILL_INDEX
    for root, dirs, files in os.walk(SKILL_DIR):
        if "SKILL.md" in files:
            name = os.path.basename(root)
            if name == "skills":
                continue
            rel = os.path.relpath(root, SKILL_DIR)
            relkey = rel.replace(os.sep, "/")
            path = os.path.join(root, "SKILL.md")
            _SKILL_INDEX[relkey] = path
            _SKILL_ALIAS.setdefault(name, []).append(relkey)
    return _SKILL_INDEX


def _skill_list():
    """Daftar skill terkelompok per layer (top-level folder)."""
    if not _SKILL_INDEX:
        return "(skill index kosong — jalankan action='reload')"
    layers = {}
    for relkey in _SKILL_INDEX:
        top = relkey.split("/")[0]
        layers.setdefault(top, []).append(relkey)
    out = ["Skills per layer (%d total):" % len(_SKILL_INDEX)]
    for top in sorted(layers):
        items = sorted(layers[top])
        out.append("\n### %s (%d)" % (top, len(items)))
        out.append("  " + " · ".join(items))
    return "\n".join(out)


def tool_skill(name=None, action="show", file=None):
    """Load Lethica skill ke context. action: list|show|reload.
    name bisa "layer/skill" (exact) atau "skill" (basename, disambiguate).
    file opsional: baca file pendukung di dlm skill dir (references/, scripts/)."""
    if action == "reload" or not _SKILL_INDEX:
        _build_skill_index()
    if action == "list" or not name:
        return _skill_list()
    # resolve key
    if name in _SKILL_INDEX:
        relkey = name
    else:
        # basename lookup
        cands = _SKILL_ALIAS.get(name, [])
        if not cands:
            # maybe 'name' is a LAYER (container) → list sub-skills
            subs = [rk for rk in _SKILL_INDEX if rk.startswith(name + "/")]
            if subs:
                return (f"Layer '{name}' adalah container ({len(subs)} sub-skill):\n"
                        + "\n".join(f"  - {s}" for s in sorted(subs))
                        + f"\nGunakan <skill name='{sorted(subs)[0]}' /> untuk load.")
            return (f"Skill '{name}' gak ketemu. list: <skill name='' action='list'/>\n"
                    f"Hint: pakai format 'layer/skill', mis. 'coding/coding'.")
        if len(cands) == 1:
            relkey = cands[0]
        else:
            return (f"Ambigu '{name}' → {len(cands)} skill:\n"
                    + "\n".join(f"  - {c}" for c in sorted(cands))
                    + "\nGunakan relkey lengkap, mis. <skill name='%s' />" % sorted(cands)[0])
    path = _SKILL_INDEX[relkey]
    if file:
        fp = os.path.normpath(os.path.join(os.path.dirname(path), file))
        if not fp.startswith(os.path.dirname(path)):
            return "Error: path file keluar dari skill dir."
        if not os.path.isfile(fp):
            return f"File '{file}' gak ada di skill '{relkey}'."
        with open(fp, encoding="utf-8", errors="replace") as f:
            return f"=== {relkey}/{file} ===\n" + f.read()[:8000]
    with open(path, encoding="utf-8", errors="replace") as f:
        return f"=== SKILL: {relkey} ===\n" + f.read()[:12000]


def tool_run_code(lang, src, timeout=30):
    import subprocess as _sp
    lang=(lang or '').lower().strip(); src=src or ''
    if not src.strip(): return '[run_code] empty source'
    wd=os.path.join(config.WORKSPACE,'.runcode'); os.makedirs(wd,exist_ok=True)
    c={'python':'python3','py':'python3','python3':'python3','node':'node','javascript':'node','js':'node','rust':'rustc','rs':'rustc','c':'gcc','cpp':'g++','c++':'g++','cc':'cc','go':'go'}
    if lang not in c: return '[run_code] unsupported lang: '+lang
    try:
        if lang in ('python','py','python3'):
            f=os.path.join(wd,'_c.py'); open(f,'w').write(src); cmd=['python3',f]
        elif lang in ('node','javascript','js'):
            f=os.path.join(wd,'_c.js'); open(f,'w').write(src); cmd=['node',f]
        elif lang in ('rust','rs'):
            f=os.path.join(wd,'_c.rs'); open(f,'w').write(src); o=os.path.join(wd,'_rs'); rc=_sp.run(['rustc',f,'-o',o],capture_output=True,text=True,timeout=timeout)
            if rc.returncode!=0: return '[rustc stderr]\n'+rc.stderr
            cmd=[o]
        elif lang in ('c','cc'):
            f=os.path.join(wd,'_c.c'); open(f,'w').write(src); o=os.path.join(wd,'_cbin'); rc=_sp.run(['gcc' if lang=='c' else 'cc',f,'-o',o],capture_output=True,text=True,timeout=timeout)
            if rc.returncode!=0: return '[gcc stderr]\n'+rc.stderr
            cmd=[o]
        elif lang in ('cpp','c++'):
            f=os.path.join(wd,'_c.cpp'); open(f,'w').write(src); o=os.path.join(wd,'_cpp'); rc=_sp.run(['g++',f,'-o',o],capture_output=True,text=True,timeout=timeout)
            if rc.returncode!=0: return '[g++ stderr]\n'+rc.stderr
            cmd=[o]
        elif lang=='go':
            f=os.path.join(wd,'_c.go'); open(f,'w').write(src); cmd=['go','run',f]
        else: return '[run_code] unsupported lang: '+lang
        r=_sp.run(cmd,capture_output=True,text=True,timeout=timeout)
        return ('[run_code lang=%s exit=%d]\n--- stdout ---\n%s\n--- stderr ---\n%s'%(lang,r.returncode,r.stdout,r.stderr))
    except _sp.TimeoutExpired: return '[run_code] TIMEOUT after %ds'%timeout
    except FileNotFoundError as e: return '[run_code] missing compiler: %s'%e
    except Exception as e: return '[run_code] ERROR: %s'%e

# ── v3.9: tool port dari Kiro Agent (adaptasi, bukan copy mentah) ──
# Semua tool di bawah OPTIONAL-by-design: cek dep/binary/env dulu,
# return pesan jelas kalau belum tersedia — tidak pernah traceback.

def _progress(label):
    if console:
        console.print(f"[dim cyan]➔ {label}[/dim cyan]")


def tool_phone_lookup(number):
    """OSINT nomor telepon offline (lib phonenumbers, opsional)."""
    try:
        import phonenumbers
        from phonenumbers import carrier, geocoder, number_type, PhoneNumberType
    except ImportError:
        return ("[phone_lookup] lib 'phonenumbers' belum ada.\n"
                "Install ke venv lethica:\n"
                "  ~/workspace/lethica/venv/bin/pip install phonenumbers")
    number = (number or "").strip()
    if not number:
        return "[phone_lookup] arg 'number' kosong."
    _progress(f"Lookup nomor: {number[:18]}")
    try:
        parsed = phonenumbers.parse(number)
    except Exception as e:
        return f"[phone_lookup] nomor tidak bisa di-parse: {e}"
    tipe_map = {PhoneNumberType.FIXED_LINE: "Fixed Line", PhoneNumberType.MOBILE: "Mobile",
                PhoneNumberType.FIXED_LINE_OR_MOBILE: "Fixed/Mobile",
                PhoneNumberType.TOLL_FREE: "Toll Free", PhoneNumberType.PREMIUM_RATE: "Premium",
                PhoneNumberType.SHARED_COST: "Shared Cost", PhoneNumberType.VOIP: "VOIP",
                PhoneNumberType.PERSONAL_NUMBER: "Personal", PhoneNumberType.PAGER: "Pager",
                PhoneNumberType.UAN: "UAN", PhoneNumberType.VOICEMAIL: "Voicemail",
                PhoneNumberType.UNKNOWN: "Unknown"}
    lines = [
        f"Nomor    : {phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.INTERNATIONAL)}",
        f"Region   : {geocoder.description_for_number(parsed, 'id') or 'N/A'}",
        f"Carrier  : {carrier.name_for_number(parsed, 'en') or 'N/A'}",
        f"Valid    : {phonenumbers.is_valid_number(parsed)}",
        f"Possible : {phonenumbers.is_possible_number(parsed)}",
        f"Tipe     : {tipe_map.get(number_type(parsed), 'Unknown')}",
        f"Country  : {phonenumbers.region_code_for_number(parsed) or 'N/A'} (+{parsed.country_code})",
    ]
    return "[phone_lookup]\n" + "\n".join(lines)


def _http_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": f"Lethica/{config.VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", errors="replace"))


def tool_gps(ip=None):
    """Lokasi: termux-location (HP) → ip-api.com → ipapi.co."""
    _progress("Cek lokasi...")
    if shutil.which("termux-location"):
        for provider in ("gps", "network", ""):
            try:
                cmd = f"termux-location -p {provider}" if provider else "termux-location"
                pr = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
                data = json.loads(pr.stdout) if pr.stdout.strip().startswith("{") else {}
                lat = data.get("latitude") or data.get("lat")
                lon = data.get("longitude") or data.get("lon")
                if lat and lon:
                    return ("[gps] sensor OK (provider: %s)\nlat=%s lon=%s akurasi=%sm alt=%s" %
                            (provider or "default", lat, lon,
                             data.get("accuracy", "?"), data.get("altitude", "?")))
            except Exception:
                pass
    target = (ip or "").strip()
    suffix = f"/{target}" if target else ""
    try:
        d = _http_json(f"http://ip-api.com/json{suffix}"
                       "?fields=status,country,countryCode,regionName,city,zip,lat,lon,timezone,isp,query")
        if d.get("status") == "success":
            return ("[gps] IP geolocation (ip-api.com, akurasi kasar)\n"
                    f"{d.get('city')}, {d.get('regionName')}, {d.get('country')} ({d.get('countryCode')})\n"
                    f"lat={d.get('lat')} lon={d.get('lon')} tz={d.get('timezone')} "
                    f"isp={d.get('isp')} ip={d.get('query')}")
    except Exception:
        pass
    try:
        d = _http_json(f"https://ipapi.co/{target}/json/" if target else "https://ipapi.co/json/")
        if d and not d.get("error"):
            return ("[gps] IP geolocation (ipapi.co, akurasi kasar)\n"
                    f"{d.get('city')}, {d.get('region')}, {d.get('country_name')}\n"
                    f"lat={d.get('latitude')} lon={d.get('longitude')} tz={d.get('timezone')} ip={d.get('ip')}")
    except Exception as e:
        return f"[gps] semua metode gagal: {e}"
    return "[gps] tidak dapat menentukan lokasi."


_MIME_BY_EXT = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp"}


def tool_image_vision(path, prompt=None, model=None):
    """Analisa gambar via model vision-capable (bukan model text-only)."""
    p = _expand(path or "")
    if not in_sandbox(p):
        return (f"[image_vision] path '{path}' OUTSIDE sandbox.\n"
                "Taruh gambar di ~/lethica/workspace/ dulu.")
    if not os.path.isfile(p):
        return f"[image_vision] file tidak ada: {path}"
    if os.path.getsize(p) > 8 * 1024 * 1024:
        return "[image_vision] file > 8MB, tolak (hemat token)."
    _progress(f"Analisa gambar: {os.path.basename(p)}")
    try:
        with open(p, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("ascii")
    except Exception as e:
        return f"[image_vision] gagal baca file: {e}"
    mime = _MIME_BY_EXT.get(os.path.splitext(p)[1].lower(), "image/png")
    mdl = (model or "").strip() or getattr(config, "VISION_MODEL", None) or config.DEFAULT_MODEL
    q = (prompt or "").strip() or "Deskripsikan gambar ini secara ringkas."
    from core import client as _client_mod  # lazy: hindari circular import
    r = _client_mod.LClient().chat(
        mdl, [{"role": "user", "content": [
            {"type": "text", "text": q},
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]}],
        max_tokens=600)
    if isinstance(r, dict) and "error" in r:
        return f"[image_vision] error dari {mdl}: {r['error']}"
    try:
        txt = (r.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    except Exception:
        txt = ""
    if not txt.strip():
        return (f"[image_vision] model {mdl} tidak mengembalikan jawaban — "
                "kemungkinan bukan model vision. Isi arg 'model' dengan model vision-capable.")
    return f"[image_vision] ({mdl})\n{txt.strip()[:3000]}"


def _email_creds():
    user = os.environ.get("LETHICA_EMAIL_USER", "").strip()
    pw = os.environ.get("LETHICA_EMAIL_PASS", "").strip()
    if not user or not pw:
        return None, ("[email] env belum diset.\n"
                      "Set LETHICA_EMAIL_USER dan LETHICA_EMAIL_PASS "
                      "(Gmail App Password: Google Account → Security → "
                      "2-Step Verification → App passwords).")
    return (user, pw), None


def tool_send_email(to, subject, body):
    """Kirim email via Gmail SMTP."""
    import smtplib
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    creds, err = _email_creds()
    if err:
        return err
    user, pw = creds
    to = (to or "").strip()
    if not to:
        return "[send_email] arg 'to' kosong."
    _progress(f"Kirim email ke: {to}")
    try:
        msg = MIMEMultipart()
        msg["From"] = user
        msg["To"] = to
        msg["Subject"] = subject or ""
        msg.attach(MIMEText(body or "", "plain", "utf-8"))
        s = smtplib.SMTP("smtp.gmail.com", 587, timeout=30)
        s.starttls()
        s.login(user, pw)
        s.sendmail(user, [to], msg.as_string())
        s.quit()
        return f"[send_email] OK terkirim ke {to} — subjek: {subject}"
    except Exception as e:
        return f"[send_email] gagal: {e}"


def _decode_hdr(h):
    from email.header import decode_header
    if not h:
        return "?"
    parts = []
    for txt, enc in decode_header(h):
        if isinstance(txt, bytes):
            try:
                parts.append(txt.decode(enc or "utf-8", errors="replace"))
            except Exception:
                parts.append(txt.decode("utf-8", errors="replace"))
        else:
            parts.append(txt)
    return "".join(parts) or "?"


def _mail_snippet(em):
    try:
        if em.is_multipart():
            for part in em.walk():
                if (part.get_content_type() == "text/plain"
                        and "attachment" not in str(part.get("Content-Disposition"))):
                    payload = part.get_payload(decode=True)
                    if payload:
                        return payload.decode(errors="replace").strip()[:150].replace("\n", " ")
        else:
            payload = em.get_payload(decode=True)
            if payload:
                return payload.decode(errors="replace").strip()[:150].replace("\n", " ")
    except Exception:
        pass
    return "(tidak bisa baca isi)"


def tool_read_inbox(limit=5, query=None):
    """Baca email terbaru via Gmail IMAP."""
    import imaplib
    import email as _email
    creds, err = _email_creds()
    if err:
        return err
    user, pw = creds
    try:
        limit = max(1, min(int(limit or 5), 20))
    except Exception:
        limit = 5
    _progress(f"Cek inbox (limit {limit})...")
    try:
        m = imaplib.IMAP4_SSL("imap.gmail.com")
        m.login(user, pw)
        m.select("inbox")
        crit = (query or "ALL").strip() or "ALL"
        _st, data = m.search(None, crit)
        ids = data[0].split()
        out = [f"[read_inbox] {len(ids)} cocok, tampil {min(limit, len(ids))} terbaru:"]
        for mid in reversed(ids[-limit:]):
            _st, md = m.fetch(mid, "(RFC822)")
            subj = frm = "?"
            snippet = ""
            for part in md:
                if isinstance(part, tuple):
                    em = _email.message_from_bytes(part[1])
                    subj = _decode_hdr(em.get("Subject"))
                    frm = _decode_hdr(em.get("From"))
                    snippet = _mail_snippet(em)
            out.append(f"— Dari: {frm}\n  Subjek: {subj}\n  Isi: {snippet}")
        m.logout()
        return "\n".join(out)
    except Exception as e:
        return f"[read_inbox] gagal: {e}"


def tool_notify_project(project, summary=None):
    """Email notifikasi 'projek selesai' ke email sendiri."""
    import socket
    import datetime as _dt
    project = (project or "").strip()
    if not project:
        return "[notify_project] arg 'project' kosong."
    me = os.environ.get("LETHICA_EMAIL_USER", "").strip()
    if not me:
        return "[notify_project] LETHICA_EMAIL_USER belum diset — tidak tahu mau kirim ke mana."
    body = (f"Projek selesai: {project}\n"
            f"Ringkasan: {summary or '-'}\n"
            f"Waktu: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Host: {socket.gethostname()}\n— Lethica")
    return tool_send_email(me, f"[Lethica] Projek selesai: {project}", body)


def _find_wordlist(wordlist):
    if wordlist:
        p = os.path.expanduser(wordlist)
        if os.path.isfile(p):
            return p
    for p in ("/usr/share/wordlists/rockyou.txt", "/usr/share/dict/words",
              os.path.expanduser("~/rockyou.txt"),
              os.path.expanduser("~/wordlists/rockyou.txt")):
        if os.path.isfile(p):
            return p
    return None


_HASHCAT_CODES = {"md5": "0", "sha1": "100", "sha256": "1400",
                  "sha512": "1700", "ntlm": "1000", "bcrypt": "3200"}


def _detect_hash_type(hv):
    hv = hv.strip()
    if hv.startswith(("$2y$", "$2a$", "$2b$")):
        return "bcrypt"
    ln = len(hv)
    if ln == 32:
        return "md5"  # ntlm bila uppercase — dicek pemanggil
    if ln == 40:
        return "sha1"
    if ln == 64:
        return "sha256"
    if ln == 128:
        return "sha512"
    return None


def tool_crack_hash(hash, type=None, wordlist=None, mode="hash"):
    """Crack hash string via hashcat, atau file (zip/ssh/dll) via john."""
    hv = (hash or "").strip()
    if not hv:
        return "[crack_hash] arg 'hash' kosong."
    mode = (mode or "hash").strip().lower()
    if mode == "file":
        john = shutil.which("john")
        if not john:
            return ("[crack_hash] binary 'john' tidak ditemukan.\n"
                    "Install: apt install john  (https://www.openwall.com/john/)")
        wl = _find_wordlist(wordlist)
        cmd = [john] + ([f"--wordlist={wl}"] if wl else []) + [hv]
        _progress("Crack file via john...")
        try:
            pr = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            show = subprocess.run([john, "--show", hv], capture_output=True, text=True, timeout=30)
            if "0 password hashes cracked" in show.stdout:
                log = (pr.stdout + pr.stderr).strip()[:1500]
                return f"[crack_hash] password tidak ketemu (coba wordlist lain).\nLog:\n{log}"
            return f"[crack_hash] john --show:\n{show.stdout.strip()[:2000]}"
        except subprocess.TimeoutExpired:
            return "[crack_hash] timeout 180s."
        except Exception as e:
            return f"[crack_hash] error: {e}"
    hc = shutil.which("hashcat")
    if not hc:
        return ("[crack_hash] binary 'hashcat' tidak ditemukan.\n"
                "Install: apt install hashcat  (butuh GPU/OpenCL untuk performa penuh)")
    htype = (type or "").strip().lower() or _detect_hash_type(hv)
    if htype == "md5" and hv.isupper():
        htype = "ntlm"
    code = _HASHCAT_CODES.get(htype or "")
    if not code:
        return (f"[crack_hash] tipe hash tidak dikenali: '{type or '?'}'. "
                "Pilih: md5, sha1, sha256, sha512, ntlm, bcrypt.")
    wl = _find_wordlist(wordlist)
    if not wl:
        return ("[crack_hash] butuh wordlist (arg 'wordlist').\n"
                "Contoh: /usr/share/wordlists/rockyou.txt — "
                "tanpa wordlist tool ini menolak jalan (no brute-force default).")
    _progress(f"Crack {htype} via hashcat...")
    import tempfile
    tf = tempfile.NamedTemporaryFile("w", suffix=".hash", delete=False)
    try:
        tf.write(hv)
        tf.close()
        pr = subprocess.run([hc, "-m", code, tf.name, wl,
                             "--quiet", "--show", "--potfile-disable"],
                            capture_output=True, text=True, timeout=180)
        out = pr.stdout.strip()
        if out and ":" in out:
            return f"[crack_hash] PASSWORD KETEMU: {out.split(':')[-1].strip()}\n(tipe: {htype})"
        err = pr.stderr.strip()[:500]
        return ("[crack_hash] tidak ketemu / gagal.\n"
                f"Output:\n{out[:1000]}\n{('Error: ' + err) if err else ''}".rstrip())
    except subprocess.TimeoutExpired:
        return "[crack_hash] timeout 180s."
    except Exception as e:
        return f"[crack_hash] error: {e}"
    finally:
        try:
            os.unlink(tf.name)
        except Exception:
            pass


def _pkt_brief(p):
    try:
        from scapy.all import IP, TCP, UDP, Raw, DNS, DNSQR
    except ImportError:
        return "?"
    if IP in p:
        src, dst = p[IP].src, p[IP].dst
        if TCP in p:
            info = f"TCP {p[TCP].sport}->{p[TCP].dport}"
            if Raw in p:
                try:
                    info += " | " + p[Raw].load.decode("utf-8", errors="ignore")[:40].replace("\n", " ")
                except Exception:
                    info += " | [biner]"
            return f"{src} -> {dst} | {info}"
        if UDP in p:
            info = f"UDP {p[UDP].sport}->{p[UDP].dport}"
            if DNS in p and p[DNS].qr == 0:
                try:
                    info += " | DNS: " + p[DNSQR].qname.decode(errors="ignore")
                except Exception:
                    pass
            return f"{src} -> {dst} | {info}"
        return f"{src} -> {dst} | proto {p[IP].proto}"
    return "non-IP"


def _proc_conns(count):
    import struct
    import socket as _sock
    def _ip(h):
        try:
            return _sock.inet_ntoa(struct.pack("<L", int(h.split(":")[0], 16)))
        except Exception:
            return h
    def _port(h):
        try:
            return int(h.split(":")[1], 16)
        except Exception:
            return 0
    states = {"01": "ESTABLISHED", "02": "SYN_SENT", "03": "SYN_RECV",
              "06": "TIME_WAIT", "0A": "LISTEN"}
    lines = ["[sniffer] live capture tidak tersedia (butuh root/scapy/tcpdump).",
             "Koneksi aktif dari /proc:"]
    n = 0
    for proto, path in (("TCP", "/proc/net/tcp"), ("UDP", "/proc/net/udp")):
        try:
            with open(path) as f:
                rows = f.read().splitlines()[1:]
        except Exception:
            continue
        for r in rows:
            if n >= count:
                break
            c = r.split()
            if len(c) < 4:
                continue
            tag = f" [{states.get(c[3], c[3])}]" if proto == "TCP" else ""
            lines.append(f"{proto}{tag} {_ip(c[1])}:{_port(c[1])} -> {_ip(c[2])}:{_port(c[2])}")
            n += 1
    if n == 0:
        lines.append("(tidak ada koneksi terbaca)")
    return "\n".join(lines)


def tool_network_sniffer(interface="any", count=10, filter=""):
    """Capture paket: scapy → tcpdump → fallback /proc (koneksi aktif)."""
    try:
        count = max(1, min(int(count or 10), 50))
    except Exception:
        count = 10
    iface = (interface or "any").strip() or "any"
    bpf = (filter or "").strip()
    _progress(f"Sniff {iface} (count {count})...")
    try:
        from scapy.all import sniff as _sniff
        pkts = _sniff(iface=iface if iface != "any" else None, count=count,
                      filter=bpf or None, timeout=15)
        if pkts:
            lines = [f"[sniffer] {len(pkts)} paket (scapy):"]
            for i, p in enumerate(pkts):
                lines.append(f"{i + 1}. {_pkt_brief(p)}")
            return "\n".join(lines)
    except ImportError:
        pass
    except Exception as e:
        if console:
            console.print(f"[dim yellow]scapy gagal: {str(e)[:80]}[/dim yellow]")
    td = shutil.which("tcpdump")
    if td:
        try:
            cmd = [td, "-i", iface, "-c", str(count), "-nn", "-q"] + ([bpf] if bpf else [])
            pr = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if pr.returncode == 0 and pr.stdout.strip():
                return f"[sniffer] tcpdump ({iface}):\n{pr.stdout.strip()[:4000]}"
        except Exception:
            pass
    return _proc_conns(count)


def tool_android_pentest(args):
    """Wrapper DroidHunter: jalankan droidhunter.py dengan argumen."""
    import shlex
    args = (args or "").strip()
    if not args:
        return "[android_pentest] arg 'args' kosong."
    cands = [os.path.expanduser("~/DroidHunter/droidhunter.py"),
             "/root/DroidHunter/droidhunter.py",
             os.path.join(config.WORKSPACE, "DroidHunter", "droidhunter.py"),
             os.path.abspath("DroidHunter/droidhunter.py")]
    dh = next((p for p in cands if os.path.isfile(p)), None) or shutil.which("droidhunter")
    if not dh:
        return ("[android_pentest] DroidHunter tidak ditemukan.\n"
                "Taruh di ~/DroidHunter/droidhunter.py atau sediakan binary 'droidhunter' di PATH.")
    _progress(f"DroidHunter: {args[:60]}")
    try:
        base = ["python3", dh] if dh.endswith(".py") else [dh]
        pr = subprocess.run(base + shlex.split(args), capture_output=True, text=True, timeout=120)
        out = pr.stdout + ("\n[stderr]\n" + pr.stderr if pr.stderr.strip() else "")
        out = out.strip()[:4000] or f"(exit {pr.returncode}, tanpa output)"
        return f"[android_pentest] exit={pr.returncode}\n{out}"
    except subprocess.TimeoutExpired:
        return "[android_pentest] timeout 120s."
    except Exception as e:
        return f"[android_pentest] error: {e}"


def _find_chromium():
    if os.path.isfile("/data/data/com.termux/files/usr/bin/chromium"):
        return "/data/data/com.termux/files/usr/bin/chromium"
    for b in ("chromium", "chromium-browser", "google-chrome", "chrome"):
        w = shutil.which(b)
        if w:
            return w
    try:
        base = os.path.expanduser("~/.cache/ms-playwright")
        if os.path.isdir(base):
            for d in sorted(os.listdir(base)):
                for name in ("headless_shell", "chrome-linux/chrome", "chrome-linux/headless_shell"):
                    p = os.path.join(base, d, name)
                    if os.path.isfile(p) and os.access(p, os.X_OK):
                        return p
    except Exception:
        pass
    return None


def tool_agent_browser(commands, chromium_path=None):
    """Browser automation via binary 'agent-browser' (Rust) + chromium."""
    import shlex
    cmds = [c.strip() for c in (commands or "").splitlines()
            if c.strip() and not c.strip().startswith("#")]
    if not cmds:
        return "[agent_browser] arg 'commands' kosong."
    ab = shutil.which("agent-browser")
    if not ab:
        return ("[agent_browser] binary 'agent-browser' tidak ditemukan di PATH.\n"
                "Install: cargo install agent-browser  (https://github.com/vercel-labs/agent-browser)")
    chrom = (chromium_path or "").strip() or _find_chromium()
    if not chrom:
        return "[agent_browser] chromium tidak ketemu. Isi arg 'chromium_path'."
    _progress(f"agent-browser: {len(cmds)} perintah...")
    out = []
    for cmd in cmds:
        try:
            pr = subprocess.run([ab, "--executable-path", chrom] + shlex.split(cmd),
                                capture_output=True, text=True, timeout=120)
            txt = pr.stdout.strip()
            if pr.stderr.strip():
                txt += "\n[stderr]\n" + pr.stderr.strip()
            out.append(f"$ agent-browser {cmd}\n{(txt.strip() or '(tanpa output)')[:3000]}")
        except subprocess.TimeoutExpired:
            out.append(f"$ agent-browser {cmd}\nTIMEOUT 120s")
        except Exception as e:
            out.append(f"$ agent-browser {cmd}\nerror: {e}")
    return "[agent_browser]\n" + "\n\n".join(out)[:6000]


def tool_hyperbrowser(task):
    """Browser cloud stealth via Hyperbrowser (butuh API key)."""
    import re as _re
    task = (task or "").strip()
    if not task:
        return "[hyperbrowser] arg 'task' kosong."
    key = os.environ.get("HYPERBROWSER_API_KEY", "").strip()
    if not key:
        return ("[hyperbrowser] env HYPERBROWSER_API_KEY belum diset.\n"
                "Daftar di hyperbrowser.ai, lalu export HYPERBROWSER_API_KEY=<key>.")
    try:
        from hyperbrowser import Hyperbrowser
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        return f"[hyperbrowser] lib belum ada: {e}\nInstall: pip install hyperbrowser playwright"
    _progress("Hyperbrowser cloud (stealth)...")
    try:
        hb = Hyperbrowser(api_key=key)
        sess = hb.sessions.create({"use_stealth": True})
        out = [f"Task: {task}"]
        urls = _re.findall(r"https?://[^\s'\"<>,]+", task)
        with sync_playwright() as p:
            br = p.chromium.connect_over_cdp(sess.ws_endpoint)
            pg = br.new_context().new_page()
            if urls:
                for u in urls[:5]:
                    try:
                        pg.goto(u, timeout=60000)
                        out.append(f"\nURL: {u}\nTitle: {pg.title()}\n{pg.inner_text('body')[:3000]}")
                    except Exception as e:
                        out.append(f"\nURL {u} gagal: {e}")
            else:
                pg.goto("https://www.google.com", timeout=60000)
                pg.fill("textarea[name=q], input[name=q]", task)
                pg.keyboard.press("Enter")
                pg.wait_for_timeout(5000)
                out.append("Search:\n" + pg.inner_text("body")[:3000])
            br.close()
        try:
            hb.sessions.close(sess.id)
        except Exception:
            pass
        return "[hyperbrowser]\n" + "\n".join(out)[:6000]
    except Exception as e:
        return f"[hyperbrowser] gagal: {e}"


# ── v2.8: stats wrapping (penting: tags.py dispatch harus pakai alias ini) ──
tool_read_file = stats.wrap("read_file", tool_read_file)
tool_write_file = stats.wrap("write_file", tool_write_file)
tool_edit_file = stats.wrap("edit_file", tool_edit_file)
tool_list_dir = stats.wrap("list_dir", tool_list_dir)
tool_search_content = stats.wrap("search_content", tool_search_content)
tool_http_request = stats.wrap("http_request", tool_http_request)
tool_download_file = stats.wrap("download_file", tool_download_file)
tool_run_command = stats.wrap("execute_command", tool_run_command)
tool_self_check = stats.wrap("self_check", tool_self_check)
tool_web_search = stats.wrap("web_search", tool_web_search)
tool_browse = stats.wrap("browse", tool_browse)
tool_memory = stats.wrap("memory", tool_memory)
tool_plan = stats.wrap("plan", tool_plan)
tool_spawn = stats.wrap("spawn", tool_spawn)
tool_skill = stats.wrap("skill", tool_skill)
tool_run_code = stats.wrap("run_code", tool_run_code)
# ── v3.9: port Kiro ──
tool_phone_lookup = stats.wrap("phone_lookup", tool_phone_lookup)
tool_gps = stats.wrap("gps", tool_gps)
tool_image_vision = stats.wrap("image_vision", tool_image_vision)
tool_send_email = stats.wrap("send_email", tool_send_email)
tool_read_inbox = stats.wrap("read_inbox", tool_read_inbox)
tool_notify_project = stats.wrap("notify_project", tool_notify_project)
tool_crack_hash = stats.wrap("crack_hash", tool_crack_hash)
tool_network_sniffer = stats.wrap("network_sniffer", tool_network_sniffer)
tool_android_pentest = stats.wrap("android_pentest", tool_android_pentest)
tool_agent_browser = stats.wrap("agent_browser", tool_agent_browser)
tool_hyperbrowser = stats.wrap("hyperbrowser", tool_hyperbrowser)

