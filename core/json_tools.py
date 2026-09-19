# core/json_tools.py — v3.0: normalizer JSON tool-call format
# Model kadang emit tool call sebagai JSON dict / function-call style
# alih-alih tag XML. Modul ini rewrite semua format itu ke tag canonical
# yang bisa di-dispatch regex tags.py.
import json
import re

# Nama tool Lethica (sinkron dgn tags.TAG_NAMES + exec)
_LETHICA_TOOLS = {
    "memory", "plan", "browse", "web_search", "read_file", "write_file",
    "list_dir", "search_content", "http_request", "download_file", "rag",
    "run_code", "exec", "edit_file",
}

# Alias nama tool asing → canonical Lethica
_NAME_ALIAS = {
    "bash": "exec", "shell": "exec", "execute_command": "exec", "terminal": "exec",
    "run_terminal": "exec", "execute_bash": "exec",
    "grep": "search_content", "search": "search_content", "search_files": "search_content",
    "glob": "search_content",
    "fs_read": "read_file", "view": "read_file", "cat": "read_file",
    "fs_write": "write_file", "save": "write_file",
    "edit": "edit_file", "str_replace": "edit_file", "str_replace_editor": "edit_file",
    "apply_patch": "edit_file",
    "ls": "list_dir", "dir": "list_dir", "list": "list_dir",
    "fetch": "http_request", "curl": "http_request",
    "download": "download_file",
    "open_browser": "browse", "browser": "browse",
    "recall": "memory", "remember": "memory",
    "task": "plan",
}

# JSON object yang keliatan kayak tool call:
#   {"name": "...", "arguments": {...}}  |  {"tool": ..., "params": {...}}
#   {"tool_calls": [...]} (wrapper OpenAI-style)
# TIDAK pakai regex (gagal di nested braces di arguments). Pakai brace-balancing
# scanner yang string-aware.
def _balanced_brace_spans(text):
    """Yield (start, end) untuk tiap span {...} seimbang di top-level.

    Menghormati string literal & escape agar kurung di dalam string
    tidak dihitung. Span tidak nested: setelah menangkap satu span,
    pemindaian dilanjutkan SETELAH penutupnya (bukan i+1), sehingga
    span di dalam span yang sudah ditangkap tidak ikut yield (menghindari
    double-convert pada wrapper {"tool_calls":[{...}]}).
    """
    spans = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] != "{":
            i += 1
            continue
        depth = 0
        j = i
        in_str = False
        esc = False
        closed = False
        while j < n:
            c = text[j]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        j += 1
                        spans.append((i, j))
                        i = j          # loncati seluruh span yg ditangkap
                        closed = True
                        break
            j += 1
        if not closed:
            i += 1
    return spans


def _convert_span(text, start, end):
    """Coba parse span sebagai tool call (wrapper atau single)."""
    raw = text[start:end]
    try:
        obj = json.loads(raw)
    except Exception:
        return None
    if not isinstance(obj, dict):
        return None
    # wrapper OpenAI-style: {"tool_calls": [...]}
    if isinstance(obj.get("tool_calls"), list):
        return _convert_wrapper_obj(obj)
    name = obj.get("name") or obj.get("tool") or obj.get("tool_name")
    canon = _canon_tool(name)
    if not canon:
        return None
    tag = _to_canonical_tag(canon, _pick_args(obj))
    return tag


def _canon_tool(name):
    name = (name or "").strip().lower()
    name = re.sub(r"^(antml:computer:|antml:)", "", name)
    if name in _LETHICA_TOOLS:
        return name
    return _NAME_ALIAS.get(name)


def _pick_args(obj):
    """Ambil dict args dari bentuk apapun: arguments / params / parameters / inline."""
    for k in ("arguments", "params", "parameters", "args", "input"):
        if isinstance(obj.get(k), dict):
            return obj[k]
    if "command" in obj and "name" not in obj:
        return obj
    return {k: v for k, v in obj.items() if k not in ("name", "tool", "tool_name", "arguments", "params", "parameters", "args", "input")}


def _to_canonical_tag(tool_name, args):
    """Args dict → tag canonical. Minimal args di-embed; full komposisi diserahkan ke tags._build_canonical."""
    args = {str(k).lower(): v for k, v in (args or {}).items()}

    # serialisasi jadi attrs atau body
    def esc(v):
        if isinstance(v, (dict, list)):
            v = json.dumps(v, ensure_ascii=False)
        s = str(v)
        return s.replace('"', '\\"').replace("\n", "\\n")

    if tool_name == "exec":
        cmd = next((args[k] for k in ("command", "cmd", "input", "code") if args.get(k)), "")
        if not cmd:
            return None
        return f'<invoke name="antml:computer:execute_command"><parameter name="command">{cmd}</parameter></invoke>'

    if tool_name == "edit_file":
        p = next((args[k] for k in ("path", "file", "filename") if args.get(k)), "")
        t = next((args[k] for k in ("target", "old", "old_string") if args.get(k)), "")
        r = next((args[k] for k in ("replacement", "new", "new_string") if args.get(k)), "")
        if not p or not t:
            return None
        return (f'<edit_file path="{esc(p)}"><target>{t}</target>'
                f'<replacement>{r}</replacement></edit_file>')

    if tool_name == "run_code":
        code = next((args[k] for k in ("code", "content", "script") if args.get(k)), "")
        if not code:
            return None
        lang = args.get("lang") or args.get("language") or "python"
        return f'<run_code lang="{esc(lang)}">{code}</run_code>'

    if tool_name == "write_file":
        p = next((args[k] for k in ("path", "file", "filename") if args.get(k)), "")
        c = next((args[k] for k in ("content", "text", "body", "data") if args.get(k)), "")
        if not p:
            return None
        return f'<write_file path="{esc(p)}">{c}</write_file>'

    # tools berbasis attrs sederhana
    attr_order = {
        "read_file": ("path", "file", "filename"),
        "list_dir": ("path", "dir", "directory"),
        "search_content": ("path", "dir", "pattern", "query", "regex", "text"),
        "web_search": ("query", "q", "text"),
        "download_file": ("url", "output"),
        "http_request": ("url", "method", "body", "headers"),
        "browse": ("url", "data", "method"),
    }
    if tool_name in attr_order:
        parts = []
        vals = {}
        for k, v in args.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            vals[k.lower()] = str(v)
        for key in attr_order[tool_name]:
            v = vals.get(key)
            if v is None:
                # alias sederhana
                aliases = {"path": ("file", "dir"), "pattern": ("query", "regex", "text"),
                           "query": ("q", "text"), "url": ("uri",)}
                for al in aliases.get(key, ()):
                    v = vals.get(al)
                    if v is not None:
                        break
            if v is not None:
                parts.append(f'{key}="{esc(v)}"')
        if not parts:
            return None
        return f"<{tool_name} " + " ".join(parts) + " />"

    if tool_name in ("memory", "plan", "rag"):
        parts = []
        for k, v in args.items():
            if isinstance(v, (dict, list)):
                v = json.dumps(v, ensure_ascii=False)
            parts.append(f'{k.lower()}="{esc(v)}"')
        return f"<{tool_name} " + " ".join(parts) + " />"

    return None


def _convert_obj(mo):
    try:
        obj = json.loads(mo.group(1))
    except Exception:
        return mo.group(0)
    if not isinstance(obj, dict):
        return mo.group(0)
    name = obj.get("name") or obj.get("tool") or obj.get("tool_name")
    canon = _canon_tool(name)
    if not canon:
        return mo.group(0)
    tag = _to_canonical_tag(canon, _pick_args(obj))
    return tag if tag else mo.group(0)


def _convert_wrapper_obj(obj):
    """{"tool_calls": [{name, arguments}, ...]} → string tag per call (or None)."""
    if not isinstance(obj, dict):
        return None
    calls = obj.get("tool_calls")
    if not isinstance(calls, list):
        return None
    out = []
    for c in calls:
        if not isinstance(c, dict):
            continue
        name = c.get("name")
        # OpenAI style: {"function": {"name": ..., "arguments": "{...json str...}"}}
        if isinstance(c.get("function"), dict):
            name = c["function"].get("name")
            raw_args = c["function"].get("arguments", {})
            if isinstance(raw_args, str):
                try:
                    raw_args = json.loads(raw_args)
                except Exception:
                    raw_args = {}
            args = raw_args
        else:
            args = _pick_args(c)
        canon = _canon_tool(name)
        if canon:
            tag = _to_canonical_tag(canon, args)
            if tag:
                out.append(tag)
    return "\n".join(out) if out else None


def normalize_json_tool_calls(reply):
    """Entry point v3.0. Rewrite JSON tool-call blocks ke tag canonical.

    Pakai brace-balancing scanner (string-aware) agar nested braces di
    field 'arguments' tidak memecah parsing. Span top-level yang bukan
    tool call dibiarkan apa adanya.
    """
    if not reply or not isinstance(reply, str):
        return reply
    result = []
    last = 0
    for start, end in _balanced_brace_spans(reply):
        converted = _convert_span(reply, start, end)
        if converted is not None:
            result.append(reply[last:start])
            result.append(converted)
            last = end
    if last:
        result.append(reply[last:])
        return "".join(result)
    return reply
