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
MEMORY_TAG_RE = re.compile(r'<memory\s+([^>]*?)/?>', re.IGNORECASE)
PLAN_TAG_RE = re.compile(r'<plan\s+([^>]*?)/?>', re.IGNORECASE)
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
tool_skill = stats.wrap("skill", tool_skill)
tool_run_code = stats.wrap("run_code", tool_run_code)

