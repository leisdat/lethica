# core/tags.py — tag sanitizers (v2.5: semua tool tag termasuk rag) + parser + dispatch
import os
import re

from core import tools, rag
from core.ui import console

# v2.5 fix: TAG_NAMES sekarang SATU sumber, include 'rag' (sebelumnya kelupaan)
TAG_NAMES = ["memory", "plan", "browse", "web_search", "read_file", "write_file",
             "list_dir", "search_content", "http_request", "download_file", "rag", "run_code", "task"]


def _fix_attr_quotes(reply):
    """Nested unescaped quotes di dalam atribut → escape."""

    def fix_tag(mo):
        tag = mo.group(0)
        out, i, n = [], 0, len(tag)
        while i < n:
            ch = tag[i]
            if ch == '"' and tag[i:i + 2] != '\\"':
                j = i + 1
                end = -1
                while j < n:
                    if tag[j] == '"' and tag[j - 1:j] != "\\":
                        rest = tag[j + 1:]
                        if re.match(r"\s+[a-zA-Z_]+\s*=|^/?\s*>|^\s*/?>", rest):
                            end = j
                            break
                    j += 1
                if end == -1:
                    end = n - 1
                val = tag[i + 1:end]
                val = val.replace('\\"', "\x22ESC\x22").replace('"', '\\"').replace("\x22ESC\x22", '\\"')
                out.append('"' + val + '"')
                i = end + 1
            else:
                out.append(ch)
                i += 1
        return "".join(out)

    for tn in TAG_NAMES:
        reply = re.sub(rf"<{tn}\b[^>]*>", fix_tag, reply, flags=re.DOTALL | re.IGNORECASE)
    return reply


def _normalize_tag_attr_order(reply):
    """Single-quote attr → double-quote, TAPI hanya quote yang jadi delimiter
    (v2.5 fix: single-quote di dalam double-quoted value gak boleh diganti)."""

    def conv(mo):
        tag = mo.group(0)
        out, i, n = [], 0, len(tag)
        while i < n:
            ch = tag[i]
            if ch in "\"'":
                quote = ch
                j = i + 1
                # cari penutup sejati: quote sama (tak ter-escape) diikuti (spasi+key= | /> | >)
                end = -1
                while j < n:
                    if tag[j] == quote and tag[j - 1:j] != "\\":
                        rest = tag[j + 1:]
                        if re.match(r"\s+[a-zA-Z_]+\s*=|^/?\s*>|^\s*/?>", rest):
                            end = j
                            break
                    j += 1
                if end == -1:
                    end = n - 1
                val = tag[i + 1:end]
                if quote == "'":
                    # single-quote delimiter → double; escape double DI DALAM yang belum escaped
                    val = re.sub(r'(?<!\\)"', '\\"', val)
                    out.append('"' + val + '"')
                else:
                    # double-quote delimiter: PERTAHANKAN escape yang sudah ada (jangan re-escape \" → \")
                    out.append('"' + val + '"')
                i = end + 1
            else:
                out.append(ch)
                i += 1
        return "".join(out)

    for tn in TAG_NAMES:
        reply = re.sub(rf"<{tn}\b[^>]*?/>", conv, reply, flags=re.DOTALL | re.IGNORECASE)
    return reply


def sanitize_tool_tags(reply):
    """Pipeline normalisa... (v3.0: JSON tool-call format → tag canonical lebih dulu)"""
    if not reply or not isinstance(reply, str):
        return reply
    # v3.0 — konversi JSON tool-call format sebelum normalisasi tag lain
    try:
        from .json_tools import normalize_json_tool_calls
        reply = normalize_json_tool_calls(reply)
    except Exception:
        pass
    reply = _normalize_foreign_tool_calls(reply)
    reply = _fix_attr_quotes(reply)
    reply = _normalize_tag_attr_order(reply)
    return reply


def _parse_tag_attrs(attrstr):
    """Parse 'key="val" key2="val2"' → dict. Escape-aware, order bebas."""
    attrs = {}
    i, n = 0, len(attrstr)
    while i < n:
        while i < n and (attrstr[i].isspace() or attrstr[i] in "/>"):
            i += 1
        j = i
        while j < n and attrstr[j] not in "= \t\n/>":
            j += 1
        name = attrstr[i:j].strip().lower()
        if not name:
            i = j + 1
            continue
        if j < n and attrstr[j] == "=":
            k = j + 1
            while k < n and attrstr[k].isspace():
                k += 1
            if k < n and attrstr[k] in "\"'":
                quote = attrstr[k]
                p = k + 1
                buf = []
                while p < n:
                    if attrstr[p] == "\\" and p + 1 < n and attrstr[p + 1] == quote:
                        buf.append(quote)
                        p += 2
                    elif attrstr[p] == "\\" and p + 1 < n and attrstr[p + 1] == "\\":
                        buf.append("\\")
                        p += 2
                    elif attrstr[p] == "\\" and p + 1 < n and attrstr[p + 1] == "n":
                        buf.append("\n")
                        p += 2
                    elif attrstr[p] == quote:
                        break
                    else:
                        buf.append(attrstr[p])
                        p += 1
                attrs[name] = "".join(buf)
                i = p + 1
            else:
                p = k
                while p < n and not attrstr[p].isspace() and attrstr[p] not in "/>":
                    p += 1
                attrs[name] = attrstr[k:p]
                i = p
        else:
            attrs[name] = "true"
            i = j
    return attrs


def _unesc(s):
    return (s or "").replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")



def _act(icon, name, detail=""):
    """Live activity indicator — kasih tau operator lagi ngapain."""
    d = (str(detail) if detail else "")[:80]
    console.print(f"[dim cyan]▌ {icon} {name}[/dim cyan] {d}")

_FENCE_LINE_RE = re.compile(r"^\s*(```|~~~)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]+`")


# ── v2.9.5: normalizer tool-call format asing ───────────────────────
# Model lemah (hy3 dkk) sering emit tool call dengan markup sendiri:
#   <tool_calls:ID>\n<tool_call:ID>execute_command">\n<parameter name="command">CMD</parameter>\n</invoke>
#   <invoke name="execute_command">...            (tanpa prefix antml:computer:)
#   <function_calls><invoke name="read_file">...</invoke></function_calls>
# Semua di-rewrite ke bentuk canonical biar regex dispatcher yang ada bisa kerja.

_TOOL_ALIASES = {
    "execute_command": "exec", "run_command": "exec", "bash": "exec", "shell": "exec",
    "terminal": "exec", "computer": "exec", "exec": "exec", "command": "exec",
    "read_file": "read_file", "read": "read_file", "cat": "read_file",
    "write_file": "write_file", "write": "write_file",
    "edit_file": "edit_file", "edit": "edit_file", "patch": "edit_file",
    "list_dir": "list_dir", "ls": "list_dir", "list_files": "list_dir",
    "search_content": "search_content", "grep": "search_content", "search": "search_content",
    "http_request": "http_request", "http": "http_request", "curl": "http_request",
    "download_file": "download_file", "download": "download_file",
    "web_search": "web_search", "search_web": "web_search",
    "browse": "browse", "fetch": "browse",
    "memory": "memory", "plan": "plan", "rag": "rag", "task": "task",
    "run_code": "run_code", "python": "run_code", "code": "run_code",
    "task": "task", "orchestrate": "task",
}

_FOREIGN_WRAPPER_RE = re.compile(
    r"<\s*/?\s*(?:tool_calls?|function_calls?)\s*:[^>\n]*>"  # bentuk ber-ID:ID
    r"|<\s*/?\s*(?:tool_calls?|function_calls?)\s*>", re.IGNORECASE)  # bentuk polos
_FUNCTION_CALLS_RE = re.compile(r"<\s*/?\s*function_calls\s*>", re.IGNORECASE)
# fragmen nama tool telanjang di awal baris:  execute_command">
_BARE_NAME_FRAG_RE = re.compile(
    r"(?m)^[ \t]*([a-zA-Z_][a-zA-Z0-9_:]*)\s*[\"']\s*>[ \t]*$")
_PARAM_BLOCK_RE = re.compile(
    r"<\s*parameter\s+name\s*=\s*[\"']([A-Za-z_][A-Za-z0-9_]*)[\"']\s*>\s*(.*?)\s*<\s*/\s*parameter\s*>",
    re.IGNORECASE | re.DOTALL)
_INVOKE_BLOCK_RE = re.compile(
    r"<\s*invoke\s+name\s*=\s*[\"']([^\"']+)[\"']\s*>(.*?)<\s*/\s*invoke\s*>",
    re.IGNORECASE | re.DOTALL)
# v2.9.6: fragmen invoke yatim — kata 'invoke name=...' tanpa kurung-siku pembuka,
# sisa setelah wrapper tool_calls dibuang, dibangun ulang jadi canonical.
_INVOKE_ORPHAN_RE = re.compile(
    r"(?m)(?<![<\w])\s*invoke\s+name\s*=\s*[\"']([^\"']+)[\"']\s*>")


def _esc_val(v, keep_newlines=False):
    """Escape value biar aman di dalam atribut double-quote."""
    v = (v or "").strip()
    if not keep_newlines:
        v = v.replace("\n", " ").replace("\r", " ")
    return v.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")


def _build_canonical(canon, params):
    """params: dict lowercased-key → value. Return canonical tag string atau None."""
    g = lambda *ks: next((params[k] for k in ks if params.get(k)), "")
    if canon == "exec":
        cmd = g("command", "cmd", "input", "code")
        if not cmd:
            return None
        return f'<invoke name="antml:computer:execute_command"><parameter name="command">{cmd}</parameter></invoke>'
    if canon == "read_file":
        p = g("path", "file", "filename")
        if not p:
            return None
        extra = ""
        if g("start"):
            extra += f' start="{_esc_val(g("start"))}"'
        if g("end"):
            extra += f' end="{_esc_val(g("end"))}"'
        return f'<read_file path="{_esc_val(p)}"{extra} />'
    if canon == "write_file":
        p, c = g("path", "file"), g("content", "text", "body", "data")
        if not p:
            return None
        app = ' append="true"' if str(g("append")).lower() in ("true", "1", "yes") else ""
        return f'<write_file path="{_esc_val(p)}"{app}>{c}</write_file>'
    if canon == "edit_file":
        p, t, r = g("path", "file"), g("target", "old", "old_string"), g("replacement", "new", "new_string")
        if not p or not t:
            return None
        return f'<edit_file path="{_esc_val(p)}"><target>{t}</target><replacement>{r}</replacement></edit_file>'
    if canon == "list_dir":
        p = g("path", "dir", "directory") or "."
        rec = ' recursive="true"' if str(g("recursive")).lower() in ("true", "1", "yes") else ""
        return f'<list_dir path="{_esc_val(p)}"{rec} />'
    if canon == "search_content":
        p, pat = g("path", "dir") or ".", g("pattern", "query", "regex", "text")
        if not pat:
            return None
        rec = ' recursive="true"' if str(g("recursive")).lower() in ("true", "1", "yes") else ""
        ic = ' ignore_case="true"' if str(g("ignore_case")).lower() in ("true", "1", "yes") else ""
        return f'<search_content path="{_esc_val(p)}" pattern="{_esc_val(pat)}"{rec}{ic} />'
    if canon == "http_request":
        u = g("url", "uri")
        if not u:
            return None
        m = f' method="{_esc_val(g("method"))}"' if g("method") else ""
        b = f' body="{_esc_val(g("body", "data"))}"' if g("body", "data") else ""
        h = f' headers="{_esc_val(g("headers"))}"' if g("headers") else ""
        return f'<http_request url="{_esc_val(u)}"{m}{b}{h} />'
    if canon == "download_file":
        u, o = g("url", "uri"), g("output", "path", "file")
        if not u or not o:
            return None
        return f'<download_file url="{_esc_val(u)}" output="{_esc_val(o)}" />'
    if canon == "web_search":
        q = g("query", "q", "text")
        if not q:
            return None
        lim = f' limit="{_esc_val(g("limit"))}"' if g("limit") else ""
        return f'<web_search query="{_esc_val(q)}"{lim} />'
    if canon == "browse":
        u = g("url", "uri")
        if not u:
            return None
        d = f' data="{_esc_val(g("data", "body"))}"' if g("data", "body") else ""
        m = f' method="{_esc_val(g("method"))}"' if g("method") else ""
        return f'<browse url="{_esc_val(u)}"{d}{m} />'
    if canon == "memory":
        a = g("action") or "load"
        k = f' key="{_esc_val(g("key", "name"))}"' if g("key", "name") else ""
        c = f' content="{_esc_val(g("content", "value"))}"' if g("content", "value") else ""
        return f'<memory action="{_esc_val(a)}"{k}{c} />'
    if canon == "plan":
        a = g("action") or "show"
        c = f' content="{_esc_val(g("content", "text"))}"' if g("content", "text") else ""
        return f'<plan action="{_esc_val(a)}"{c} />'
    if canon == "rag":
        a = g("action") or "search"
        q = f' query="{_esc_val(g("query", "q"))}"' if g("query", "q") else ""
        return f'<rag action="{_esc_val(a)}"{q} />'
    if canon == "run_code":
        lang = g("lang", "language") or "python"
        code = g("code", "content", "script")
        if not code:
            return None
        to = f' timeout="{_esc_val(g("timeout"))}"' if g("timeout") else ""
        return f'<run_code lang="{_esc_val(lang)}"{to}>{code}</run_code>'
    return None


def _canon_name(name):
    """'execute_command' / 'antml:computer:execute_command' / 'Bash' → 'exec' dst."""
    n = (name or "").strip().lower()
    if not n:
        return None
    # canonical antml prefix → sudah bener, biarkan
    if "antml" in n and n.endswith("execute_command"):
        return None  # sudah canonical, jangan diutak-atik
    n = n.split(":")[-1]
    return _TOOL_ALIASES.get(n)


def _normalize_foreign_tool_calls(reply):
    """Rewrite markup tool-call non-canonical → canonical tag. Return reply baru."""
    if not reply or not isinstance(reply, str):
        return reply
    if not re.search(r"<\s*/?\s*(?:tool_calls?|function_calls?)\b|<\s*invoke\b", reply, re.IGNORECASE):
        return reply
    r = _FOREIGN_WRAPPER_RE.sub("", reply)
    r = _FUNCTION_CALLS_RE.sub("", r)
    r = _BARE_NAME_FRAG_RE.sub(lambda m: f'<invoke name="{m.group(1)}">', r)
    r = _INVOKE_ORPHAN_RE.sub(lambda m: chr(60) + f'invoke name="{m.group(1)}">', r)

    def _rebuild(mo):
        raw_name, body = mo.group(1), mo.group(2)
        canon = _canon_name(raw_name)
        if not canon:
            return mo.group(0)  # bukan tool yang dikenal / sudah canonical
        params = {}
        for k, v in _PARAM_BLOCK_RE.findall(body):
            params[k.strip().lower()] = _unesc(v.strip())
        tag = _build_canonical(canon, params)
        return tag if tag else mo.group(0)

    r = _INVOKE_BLOCK_RE.sub(_rebuild, r)
    return r


def looks_like_tool_attempt(reply):
    """True kalau reply kelihatan MAU panggil tool tapi formatnya rusak/gak dikenal.
    Dipakai loop.py sebagai safety-net: jangan berhenti, minta model pakai format canonical."""
    if not reply or not isinstance(reply, str):
        return False
    return bool(re.search(
        r"<\s*/?\s*(?:tool_calls?|function_calls?|invoke|parameter)\b"
        r"|<\s*tool_call\b"
        r"|\b(?:execute_command|read_file|write_file|edit_file|list_dir|search_content"
        r"|http_request|download_file|web_search|browse|run_code)\s*[\"']\s*>",
        reply, re.IGNORECASE))


def _mask_code_blocks(reply):
    """Span-preserving mask: isi fenced code block + inline code span diganti \x00
    biar TAG_RE gak eksekusi tag literal yang ditulis sebagai CONTOH di prose.
    Panjang dipertahankan -> offset finditer/group tetap valid."""
    lines = reply.split("\n")
    in_fence = False
    for idx, ln in enumerate(lines):
        if _FENCE_LINE_RE.match(ln):
            in_fence = not in_fence
            continue
        if in_fence:
            lines[idx] = "\x00" * len(ln)
    reply = "\n".join(lines)
    return _INLINE_CODE_RE.sub(lambda m: "\x00" * len(m.group(0)), reply)


def dispatch(reply, agent_path):
    """Extract and execute all tool calls from reply. Return tool_outputs string."""
    # v2.9.5: mask code block DULU (span-preserving) baru normalisasi — biar markup asing
    # yang cuma CONTOH di fenced/inline code gak ikut dinormalisasi jadi tag nyata (jaga v2.8.10).
    reply = _mask_code_blocks(reply)
    reply = sanitize_tool_tags(reply)
    outputs = []
    for m in tools.READ_TAG_RE.finditer(reply):
        _act("📖", "read_file", m.group(1))
        outputs.append(f"[read_file]\n{tools.tool_read_file(m.group(1), m.group(2), m.group(3))}")
    for m in tools.WRITE_TAG_RE.finditer(reply):
        _act("✍️", "write_file", m.group(1))
        outputs.append(f"[write_file]\n{tools.tool_write_file(m.group(1), _unesc(m.group(3)), append=(m.group(2) == 'true'))}")
    for m in tools.EDIT_TAG_RE.finditer(reply):
        _act("🛠️", "edit_file", m.group(1))
        path = m.group(1)
        out = tools.tool_edit_file(path, _unesc(m.group(2)), _unesc(m.group(3)))
        if os.path.abspath(path) == agent_path:
            out += "\n" + tools.tool_self_check()
        outputs.append(f"[edit_file]\n{out}")
    for m in tools.LIST_TAG_RE.finditer(reply):
        _act("📂", "list_dir", m.group(1))
        outputs.append(f"[list_dir]\n{tools.tool_list_dir(m.group(1), m.group(2) or 'false')}")
    for m in tools.SEARCH_TAG_RE.finditer(reply):
        _act("🔍", "search_content", m.group(1))
        outputs.append(f"[search_content]\n{tools.tool_search_content(m.group(1), _unesc(m.group(2)), m.group(3) or 'false', m.group(4) or 'false')}")
    for m in tools.HTTP_TAG_RE.finditer(reply):
        _act("🌐", "http_request", m.group(1))
        outputs.append(f"[http_request]\n{tools.tool_http_request(m.group(1), m.group(2) or 'GET', m.group(4), m.group(3))}")
    for m in tools.DL_TAG_RE.finditer(reply):
        _act("⬇️", "download_file", m.group(1))
        outputs.append(f"[download_file]\n{tools.tool_download_file(m.group(1), m.group(2))}")
    for m in tools.WEBSEARCH_TAG_RE.finditer(reply):
        a = _parse_tag_attrs(m.group(1))
        _act("🔎", "web_search", a.get('query', ''))
        outputs.append(f"[web_search]\n{tools.tool_web_search(_unesc(a.get('query', '')), a.get('limit'))}")
    for m in tools.BROWSE_TAG_RE.finditer(reply):
        a = _parse_tag_attrs(m.group(1))
        outputs.append(f"[browse]\n{tools.tool_browse(_unesc(a.get('url') or tools.BROWSER_LAST_URL[0] or ''), _unesc(a['data']) if a.get('data') else None, a.get('method', 'GET'))}")
    for m in tools.MEMORY_TAG_RE.finditer(reply):
        a = _parse_tag_attrs(m.group(1))
        outputs.append(f"[memory]\n{tools.tool_memory(a.get('action'), _unesc(a['key']) if a.get('key') else None, _unesc(a['content']) if a.get('content') else None)}")
    for m in tools.PLAN_TAG_RE.finditer(reply):
        a = _parse_tag_attrs(m.group(1))
        outputs.append(f"[plan]\n{tools.tool_plan(a.get('action'), _unesc(a['content']) if a.get('content') else None)}")
    for m in rag.RAG_TAG_RE.finditer(reply):
        a = _parse_tag_attrs(m.group(1))
        outputs.append(f"[rag]\n{rag.tool_rag(a.get('action', 'search'), a.get('query'))}")
    for m in tools.EXEC_TAG_RE.finditer(reply):
        cmd = m.group(1).strip()
        _act("💻", "execute_command", cmd[:80])
        outputs.append(f"[execute_command]\n{tools.tool_run_command(cmd)}")
    for m in tools.RUNCODE_TAG_RE.finditer(reply):
        _act("⚙️", "run_code", m.group(1))
        outputs.append(f"[run_code]\n{tools.tool_run_code(m.group(1), _unesc(m.group(3)), int(m.group(2) or 30))}")
    TASK_TAG_RE = __import__("re").compile(r"<task\s+([^>]*?)/?>", __import__("re").IGNORECASE)
    for m in TASK_TAG_RE.finditer(reply):
        a = _parse_tag_attrs(m.group(1))
        goal = _unesc(a.get("goal") or "")
        _act("🛰️", "task", goal[:60])
        try:
            from core import orchestra  # lazy: hindari circular import
            outputs.append(f"[task]\n{orchestra.cli_report(goal)}")
        except Exception as ex:
            outputs.append(f"[task]\nError orchestrator: {ex}")
    for m in tools.SKILL_TAG_RE.finditer(reply):
        a = _parse_tag_attrs(m.group(1))
        name = a.get('name')
        if not name:
            name = a.get('query')  # allow <skill query='...'/>
        action = (a.get('action') or 'show').lower()
        file = a.get('file')
        _act("🎯", "skill", name or action)
        outputs.append(f"[skill]\n{tools.tool_skill(name, action, file)}")
    return "\n\n".join(outputs) if outputs else ""


def strip_tags(reply):
    """Buang semua markup tool (canonical + asing) biar user gak lihat tag soup."""
    if not reply or not isinstance(reply, str):
        return reply or ""
    reply = _FOREIGN_WRAPPER_RE.sub("", reply)
    reply = _FUNCTION_CALLS_RE.sub("", reply)
    reply = re.sub(r"</?function_calls>", "", reply, flags=re.IGNORECASE)
    reply = re.sub(r"<invoke.*?</invoke>", "", reply, flags=re.DOTALL | re.IGNORECASE)
    reply = re.sub(r"<parameter\b[^>]*>.*?</parameter>", "", reply, flags=re.DOTALL | re.IGNORECASE)
    reply = re.sub(r"<\s*(?:tool_call|invoke)\b[^>]*>", "", reply, flags=re.IGNORECASE)
    # v2.9.5: sisa fragmen markup asing (nama tool telanjang + closing tag nyasar)
    reply = _BARE_NAME_FRAG_RE.sub("", reply)
    reply = re.sub(r"</\s*(?:invoke|parameter|tool_call|tool_calls|function_calls)\s*>", "", reply, flags=re.IGNORECASE)
    for tn in TAG_NAMES:
        reply = re.sub(rf"<{tn}\b[^>]*?/>", "", reply, flags=re.DOTALL | re.IGNORECASE)
        reply = re.sub(rf"<{tn}\b[^>]*?>.*?</{tn}>", "", reply, flags=re.DOTALL | re.IGNORECASE)
    return reply.strip()
