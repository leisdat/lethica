# core/tools_mem.py — v3.7.2 Lethica tools: memory bank / plan / skill loader / run_code.
# Split dari tools.py.
import os
import re
import json
import subprocess as _sp

from core import config


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
    _SKILL_ALIAS menyimpan pemetaan basename -> [relkey] untuk resolve ambigu."""
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
    lang = (lang or '').lower().strip()
    src = src or ''
    if not src.strip():
        return '[run_code] empty source'
    wd = os.path.join(config.WORKSPACE, '.runcode')
    os.makedirs(wd, exist_ok=True)
    c = {'python': 'python3', 'py': 'python3', 'python3': 'python3', 'node': 'node',
         'javascript': 'node', 'js': 'node', 'rust': 'rustc', 'rs': 'rustc', 'c': 'gcc',
         'cpp': 'g++', 'c++': 'g++', 'cc': 'cc', 'go': 'go'}
    if lang not in c:
        return '[run_code] unsupported lang: ' + lang
    try:
        if lang in ('python', 'py', 'python3'):
            f = os.path.join(wd, '_c.py')
            open(f, 'w').write(src)
            cmd = ['python3', f]
        elif lang in ('node', 'javascript', 'js'):
            f = os.path.join(wd, '_c.js')
            open(f, 'w').write(src)
            cmd = ['node', f]
        elif lang in ('rust', 'rs'):
            f = os.path.join(wd, '_c.rs')
            open(f, 'w').write(src)
            o = os.path.join(wd, '_rs')
            rc = _sp.run(['rustc', f, '-o', o], capture_output=True, text=True, timeout=timeout)
            if rc.returncode != 0:
                return '[rustc stderr]\n' + rc.stderr
            cmd = [o]
        elif lang in ('c', 'cc'):
            f = os.path.join(wd, '_c.c')
            open(f, 'w').write(src)
            o = os.path.join(wd, '_cbin')
            rc = _sp.run(['gcc' if lang == 'c' else 'cc', f, '-o', o], capture_output=True, text=True, timeout=timeout)
            if rc.returncode != 0:
                return '[gcc stderr]\n' + rc.stderr
            cmd = [o]
        elif lang in ('cpp', 'c++'):
            f = os.path.join(wd, '_c.cpp')
            open(f, 'w').write(src)
            o = os.path.join(wd, '_cpp')
            rc = _sp.run(['g++', f, '-o', o], capture_output=True, text=True, timeout=timeout)
            if rc.returncode != 0:
                return '[g++ stderr]\n' + rc.stderr
            cmd = [o]
        elif lang == 'go':
            f = os.path.join(wd, '_c.go')
            open(f, 'w').write(src)
            cmd = ['go', 'run', f]
        else:
            return '[run_code] unsupported lang: ' + lang
        r = _sp.run(cmd, capture_output=True, text=True, timeout=timeout)
        return ('[run_code lang=%s exit=%d]\n--- stdout ---\n%s\n--- stderr ---\n%s'
                % (lang, r.returncode, r.stdout, r.stderr))
    except _sp.TimeoutExpired:
        return '[run_code] TIMEOUT after %ds' % timeout
    except FileNotFoundError as e:
        return '[run_code] missing compiler: %s' % e
    except Exception as e:
        return '[run_code] ERROR: %s' % e
