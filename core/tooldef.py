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
    "spawn": dict(
        fn="tool_spawn", icon="🚀", aliases=("subagent", "subagents", "spawn_subagents"),
        desc="Sub-agent paralel: delegasikan subtask independen ke N agent mini yang jalan bareng; hasil diagregat otomatis.",
        params={
            "tasks": ("string", True, "JSON [{\"name\":\"a\",\"task\":\"...\"}] atau baris 'nama: task'"),
            "max_rounds": ("integer", False, "Max tool rounds per sub-agent, default 4"),
        }),
    # ── v3.9: port Kiro Agent (semua OPTIONAL-by-design: cek dep/binary/env dulu) ──
    "phone_lookup": dict(
        fn="tool_phone_lookup", icon="📞", aliases=("phone", "cek_nomor"),
        desc="OSINT nomor telepon offline: operator, region, valid/tidak. Butuh lib 'phonenumbers' (opsional).",
        params={
            "number": ("string", True, "Nomor telepon, mis. +6281234567890"),
        }),
    "gps": dict(
        fn="tool_gps", icon="📍", aliases=("geolocate", "lokasi", "geolocation"),
        desc="Lokasi perangkat: termux-location (HP) → IP geolocation ip-api.com → ipapi.co.",
        params={
            "ip": ("string", False, "IP spesifik untuk geolokasi; kosong = IP sendiri"),
        }),
    "image_vision": dict(
        fn="tool_image_vision", icon="👁️", aliases=("vision", "analisa_gambar"),
        desc="Analisa gambar via model vision. BUTUH model vision-capable — model Dahl pool text-only, jadi isi arg 'model' bila perlu.",
        params={
            "path": ("string", True, "Path gambar (dalam sandbox)"),
            "prompt": ("string", False, "Pertanyaan/instruksi soal gambar"),
            "model": ("string", False, "Model vision, mis. gpt-4o. Default: VISION_MODEL / model default"),
        }),
    "send_email": dict(
        fn="tool_send_email", icon="✉️", aliases=("email", "kirim_email"),
        desc="Kirim email via Gmail SMTP. Butuh env LETHICA_EMAIL_USER + LETHICA_EMAIL_PASS (app password).",
        params={
            "to": ("string", True, "Alamat tujuan"),
            "subject": ("string", True, "Subjek"),
            "body": ("string", True, "Isi email"),
        }),
    "read_inbox": dict(
        fn="tool_read_inbox", icon="📥", aliases=("inbox", "cek_email"),
        desc="Baca email terbaru via Gmail IMAP. Env sama seperti send_email.",
        params={
            "limit": ("integer", False, "Jumlah email, default 5, maks 20"),
            "query": ("string", False, "Kriteria IMAP, mis. 'UNSEEN'. Default ALL"),
        }),
    "notify_project": dict(
        fn="tool_notify_project", icon="🔔", aliases=("notify",),
        desc="Kirim email notifikasi 'projek selesai' ke email sendiri.",
        params={
            "project": ("string", True, "Nama projek"),
            "summary": ("string", False, "Ringkasan hasil"),
        }),
    "crack_hash": dict(
        fn="tool_crack_hash", icon="🔓", aliases=("crack",),
        desc="Crack hash via hashcat / file via john. Butuh binary terinstall + wordlist (wajib). Cek dulu sebelum jalan.",
        params={
            "hash": ("string", True, "Hash string, atau path file untuk mode=file"),
            "type": ("string", False, "md5|sha1|sha256|sha512|ntlm|bcrypt (auto-detect bila kosong)"),
            "wordlist": ("string", False, "Path wordlist"),
            "mode": (("hash", "file"), False, "hash=string via hashcat, file=john. Default hash"),
        }),
    "network_sniffer": dict(
        fn="tool_network_sniffer", icon="📡", aliases=("sniff",),
        desc="Capture paket: scapy → tcpdump → fallback /proc (koneksi aktif). Butuh root untuk live capture.",
        params={
            "interface": ("string", False, "Interface, default 'any'"),
            "count": ("integer", False, "Jumlah paket/koneksi, default 10, maks 50"),
            "filter": ("string", False, "Filter BPF, mis. 'port 80'"),
        }),
    "android_pentest": dict(
        fn="tool_android_pentest", icon="🤖", aliases=("droidhunter",),
        desc="Jalankan DroidHunter dengan argumen. Butuh ~/DroidHunter/droidhunter.py atau binary di PATH.",
        params={
            "args": ("string", True, "Argumen untuk droidhunter.py"),
        }),
    "agent_browser": dict(
        fn="tool_agent_browser", icon="🌐", aliases=("abrowser",),
        desc="Browser automation via binary 'agent-browser' (Rust) + chromium. Butuh binary terinstall.",
        params={
            "commands": ("string", True, "Perintah agent-browser, satu per baris"),
            "chromium_path": ("string", False, "Path chromium; auto-detect bila kosong"),
        }),
    "hyperbrowser": dict(
        fn="tool_hyperbrowser", icon="☁️", aliases=("hbrowser",),
        desc="Browser cloud stealth via Hyperbrowser. Butuh env HYPERBROWSER_API_KEY + lib hyperbrowser/playwright.",
        params={
            "task": ("string", True, "Tugas; URL di dalamnya dibuka otomatis, atau jadi query search"),
        }),
}

# Urutan eksekusi antar-tipe = urutan dispatch historis tags.py
# (read dulu, exec belakangan — determinisme output dipertahankan).
EXEC_ORDER = ["read_file", "write_file", "edit_file", "list_dir", "search_content",
              "http_request", "download_file", "web_search", "browse", "memory",
              "plan", "rag", "exec", "run_code", "task", "spawn", "skill",
              # v3.9 port Kiro: baca-ish dulu, lalu yang butuh env/binary, exec-ish paling akhir
              "phone_lookup", "gps", "image_vision", "send_email", "read_inbox",
              "notify_project", "agent_browser", "hyperbrowser",
              "crack_hash", "network_sniffer", "android_pentest"]
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
