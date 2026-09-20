# core/tooldef.py — v3.7: SATU sumber definisi tool (skema JSON + validator)
# Dipakai dua jalur:
#   1. Native function calling — openai_tools() → payload `tools` OpenAI-compatible
#      (client.py); respons tool_calls → dispatch_calls() (tags.py) eksekusi langsung.
#   2. Tag path — validate() dipakai tags.py: error EKSPLISIT ketimbang silent-fail.
# Validator stdlib-only (zero-dep, deterministik — konsisten misi Lethica).
import json
import re

# Param: nama -> (tipe, wajib, deskripsi).
# tipe: "string" | "integer" | "boolean" | tuple(enum pilihan).
TOOL_DEFS = {
    "exec": dict(
        fn="tool_run_command", icon="💻", aliases=("execute_command",),
        desc="Jalankan perintah shell di sandbox workspace.",
        params={
            "command": ("string", True, "Perintah shell lengkap"),
            "timeout": ("integer", False, "Timeout detik, default 120"),
        }),
    "read_file": dict(
        fn="tool_read_file", icon="📖",
        desc="Baca file, opsional rentang baris start/end.",
        params={
            "path": ("string", True, "Path absolut file"),
            "start": ("integer", False, "Baris awal"),
            "end": ("integer", False, "Baris akhir"),
        }),
    "write_file": dict(
        fn="tool_write_file", icon="✍️",
        desc="Tulis atau append file.",
        params={
            "path": ("string", True, "Path absolut file"),
            "content": ("string", True, "Isi file"),
            "append": ("boolean", False, "true untuk append, default false"),
        }),
    "edit_file": dict(
        fn="tool_edit_file", icon="🛠️",
        desc="Patch presisi: ganti teks target dengan replacement (target harus unik di file).",
        params={
            "path": ("string", True, "Path absolut file"),
            "target": ("string", True, "Teks lama exact"),
            "replacement": ("string", True, "Teks baru"),
        }),
    "list_dir": dict(
        fn="tool_list_dir", icon="📂",
        desc="Daftar isi direktori.",
        params={
            "path": ("string", True, "Path direktori"),
            "recursive": ("boolean", False, "true untuk rekursif"),
        }),
    "search_content": dict(
        fn="tool_search_content", icon="🔍",
        desc="Regex search isi file (grep).",
        params={
            "path": ("string", True, "File atau direktori target"),
            "pattern": ("string", True, "Regex pattern"),
            "recursive": ("boolean", False, "true untuk rekursif"),
            "ignore_case": ("boolean", False, "case insensitive"),
        }),
    "http_request": dict(
        fn="tool_http_request", icon="🌐",
        desc="HTTP request dengan metode/body/headers (JSON di-respons rapi).",
        params={
            "url": ("string", True, "URL target"),
            "method": (("GET", "POST", "PUT", "DELETE", "PATCH"), False, "Metode HTTP, default GET"),
            "headers": ("string", False, "JSON dict header"),
            "body": ("string", False, "Body request"),
        }),
    "download_file": dict(
        fn="tool_download_file", icon="⬇️",
        desc="Unduh file ke path output.",
        params={
            "url": ("string", True, "URL sumber"),
            "output": ("string", True, "Path file hasil"),
        }),
    "web_search": dict(
        fn="tool_web_search", icon="🔎",
        desc="Search web, Bing dengan fallback DDG lite.",
        params={
            "query": ("string", True, "Query pencarian"),
            "limit": ("integer", False, "Jumlah hasil, default 5"),
        }),
    "browse": dict(
        fn="tool_browse", icon="🧭",
        desc="Browser session dengan cookie jar persist, form/POST didukung.",
        params={
            "url": ("string", False, "URL, kosong berarti lanjut di URL terakhir"),
            "data": ("string", False, "Form body misal a=b&c=d"),
            "method": ("string", False, "GET atau POST"),
        }),
    "memory": dict(
        fn="tool_memory", icon="🧠",
        desc="Memory bank permanen.",
        params={
            "action": (("save", "load", "search", "forget"), False, "Aksi memory, default load"),
            "key": ("string", False, "Kunci entri"),
            "content": ("string", False, "Isi untuk save"),
        }),
    "plan": dict(
        fn="tool_plan", icon="🗺️",
        desc="Plan mode.",
        params={
            "action": (("save", "append", "show", "clear"), False, "Aksi plan, default show"),
            "content": ("string", False, "Isi plan"),
        }),
    "rag": dict(
        fn="tool_rag", icon="📚",
        desc="Full-text search FTS5 semua file project.",
        params={
            "action": (("search", "rebuild", "stats"), False, "Aksi RAG, default search"),
            "query": ("string", False, "Kata kunci"),
        }),
    "run_code": dict(
        fn="tool_run_code", icon="⚙️",
        desc="Jalankan snippet python/bash dengan timeout.",
        params={
            "lang": ("string", True, "Bahasa: python atau bash"),
            "code": ("string", True, "Sumber kode"),
            "timeout": ("integer", False, "Timeout detik, default 30"),
        }),
    "task": dict(
        fn=None, icon="🛰️", aliases=("orchestrate",),
        # lazy: orchestra.cli_report (hindari circular import tags→orchestra)
        desc="Orkestrasi multi-step task kompleks: planner + executor + verifier.",
        params={
            "goal": ("string", True, "Deskripsi goal task"),
        }),
    "skill": dict(
        fn="tool_skill", icon="🎯",
        desc="Load atau cari skill.",
        params={
            "name": ("string", False, "Nama skill, format layer/skill"),
            "action": (("show", "list", "search"), False, "Aksi skill, default show"),
            "file": ("string", False, "File pendukung dalam skill"),
        }),
}

# Urutan eksekusi antar-tipe = urutan dispatch historis tags.py
# (read dulu, exec belakangan — determinisme output dipertahankan).
EXEC_ORDER = ["read_file", "write_file", "edit_file", "list_dir", "search_content",
              "http_request", "download_file", "web_search", "browse", "memory",
              "plan", "rag", "exec", "run_code", "task", "skill"]
_ORDER_RANK = {n: i for i, n in enumerate(EXEC_ORDER)}

_BOOL_TRUE = {"true", "1", "yes", "y", "on"}
_BOOL_FALSE = {"false", "0", "no", "n", "off", ""}
_INT_RE = re.compile(r"-?\d+")

# nama alias (asing/legacy) → canonical; diisi dari TOOL_DEFS.aliases + keys
_NAME_ALIAS = {}
for _k, _d in TOOL_DEFS.items():
    _NAME_ALIAS[_k] = _k
    _NAME_ALIAS[_k.replace("_", "")] = _k      # readfile → read_file
    for _a in _d.get("aliases", ()):
        _NAME_ALIAS[_a] = _k
_NAME_ALIAS["run_command"] = "exec"
_NAME_ALIAS["bash"] = "exec"
_NAME_ALIAS["shell"] = "exec"
_NAME_ALIAS["terminal"] = "exec"
_NAME_ALIAS["command"] = "exec"
_NAME_ALIAS["computer"] = "exec"
_NAME_ALIAS["grep"] = "search_content"
_NAME_ALIAS["search"] = "search_content"
_NAME_ALIAS["search_files"] = "search_content"
_NAME_ALIAS["cat"] = "read_file"
_NAME_ALIAS["read"] = "read_file"
_NAME_ALIAS["write"] = "write_file"
_NAME_ALIAS["edit"] = "edit_file"
_NAME_ALIAS["patch"] = "edit_file"
_NAME_ALIAS["ls"] = "list_dir"
_NAME_ALIAS["list_files"] = "list_dir"
_NAME_ALIAS["http"] = "http_request"
_NAME_ALIAS["curl"] = "http_request"
_NAME_ALIAS["download"] = "download_file"
_NAME_ALIAS["search_web"] = "web_search"
_NAME_ALIAS["fetch"] = "browse"
_NAME_ALIAS["python"] = "run_code"
_NAME_ALIAS["code"] = "run_code"
_NAME_ALIAS["recall"] = "memory"
_NAME_ALIAS["remember"] = "memory"


def canon_tool(name):
    "'execute_command'/'Bash'/'antml:computer:execute_command' → canonical. None jika asing."
    n = (name or "").strip().lower()
    if not n:
        return None
    n = n.split(":")[-1].strip()
    return _NAME_ALIAS.get(n) or _NAME_ALIAS.get(n.replace("_", ""))


def validate(name, args):
    """Validasi + coerce arg satu tool call terhadap skema TOOL_DEFS.

    args: dict raw — value string (dari tag) atau JSON asli (dari native FC).
    Return (clean_args, errors, warnings).
    errors tidak kosong → pemanggil WAJIB skip eksekusi dan laporkan errornya
    (anti silent-fail: regex lama cuma return '' tanpa sebab).
    """
    d = TOOL_DEFS.get(name)
    if not d:
        return {}, [f"tool '{name}' tidak dikenal"], []
    clean, errors, warnings = {}, [], []
    lowered = {str(k).strip().lower(): v for k, v in (args or {}).items()}
    for pname, (ptype, preq, _desc) in d["params"].items():
        if pname not in lowered:
            if preq:
                errors.append(f"arg wajib '{pname}' hilang")
            continue
        raw = lowered.pop(pname)
        if isinstance(raw, (dict, list)):  # struktur JSON → string (tool fn lama)
            raw = json.dumps(raw, ensure_ascii=False)
        val = raw
        if isinstance(ptype, tuple):  # enum — case-insensitive, simpan versi kanonik
            sval = ("" if raw is None else str(raw)).strip().lower()
            opt = next((o for o in ptype if o.lower() == sval), None)
            if opt is not None:
                val = opt
            elif sval == "" and not preq:
                continue
            else:
                errors.append(f"arg '{pname}' harus salah satu dari "
                              f"{list(ptype)}, dapat {raw!r}")
                continue
        elif ptype == "integer":
            sval = ("" if raw is None else str(raw)).strip()
            if type(raw) is int or _INT_RE.fullmatch(sval or "x"):
                val = int(sval)
            elif sval == "":
                if preq:
                    errors.append(f"arg wajib '{pname}' kosong")
                continue
            else:
                errors.append(f"arg '{pname}' harus integer, dapat {raw!r}")
                continue
        elif ptype == "boolean":
            if isinstance(raw, bool):
                val = raw
            else:
                low = ("" if raw is None else str(raw)).strip().lower()
                if low in _BOOL_TRUE:
                    val = True
                elif low in _BOOL_FALSE:
                    val = False
                else:
                    errors.append(f"arg '{pname}' harus boolean true/false, dapat {raw!r}")
                    continue
        elif ptype == "string":
            sval = "" if raw is None else str(raw)
            if preq and not sval.strip():
                errors.append(f"arg wajib '{pname}' kosong")
                continue
            val = raw  # string: JANGAN di-strip (isi file harus utuh)
        clean[pname] = val
    if lowered:
        warnings.append("arg tak dikenal dibuang: " + ", ".join(sorted(lowered)))
    return clean, errors, warnings


def openai_tools():
    """Ekspor skema jadi payload `tools` OpenAI-compatible (native FC)."""
    out = []
    for name, d in TOOL_DEFS.items():
        props, required = {}, []
        for pname, (ptype, preq, pdesc) in d["params"].items():
            schema = {"type": "string", "enum": list(ptype)} if isinstance(ptype, tuple) \
                else {"type": ptype}
            if pdesc:
                schema["description"] = pdesc
            props[pname] = schema
            if preq:
                required.append(pname)
        out.append({
            "type": "function",
            "function": {
                "name": name,
                "description": d["desc"],
                "parameters": {"type": "object", "properties": props,
                               "required": required},
            },
        })
    return out


def sort_key(call):
    """Urutkan batch tool_calls native FC mengikuti EXEC_ORDER historis."""
    return _ORDER_RANK.get(call[0], 99)
