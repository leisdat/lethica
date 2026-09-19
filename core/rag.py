# core/rag.py — RAG workspace index (SQLite FTS5, zero-dep)
import os
import re
import sqlite3

from core import config

RAG_DB = os.path.join(config.LETHICA_DIR, "workspace-index.db")
RAG_EXTS = {".py", ".md", ".txt", ".json", ".toml", ".js", ".sh", ".yaml", ".yml", ".html", ".css", ".csv", ".log"}
RAG_SKIP_DIRS = {"__pycache__", ".git", "node_modules", "backups", "deprecated", "snapshots"}
RAG_CHUNK = 800

RAG_TAG_RE = re.compile(r'<rag\s+([^>]*?)/?>', re.IGNORECASE)


def _rag_db():
    conn = sqlite3.connect(RAG_DB)
    conn.execute("""CREATE VIRTUAL TABLE IF NOT EXISTS idx USING fts5(
        path, chunk_idx, text, tokenize='unicode61 remove_diacritics 2')""")
    return conn


def _search_rows(conn, query, limit=8):
    """FTS5 search dengan fallback quoted phrase. Return rows atau None kalau invalid."""
    try:
        return conn.execute(
            "SELECT path, chunk_idx, snippet(idx, 2, '[', ']', '...', 12) FROM idx WHERE idx MATCH ? ORDER BY rank LIMIT ?",
            (query, limit)).fetchall()
    except sqlite3.OperationalError:
        pass
    try:
        return conn.execute(
            "SELECT path, chunk_idx, snippet(idx, 2, '[', ']', '...', 12) FROM idx WHERE idx MATCH ? ORDER BY rank LIMIT ?",
            ('"' + query.replace('"', '') + '"', limit)).fetchall()
    except sqlite3.OperationalError:
        return None


def tool_rag(action="search", query=None, rebuild="false"):
    """RAG: index & search semua file teks di ~/lethica."""
    action = (action or "search").lower()
    try:
        conn = _rag_db()
        if action == "rebuild":
            conn.execute("DELETE FROM idx")
            n_files, n_chunks = 0, 0
            roots = [config.WORKSPACE, config.MEMORY_DIR, config.PLAN_DIR]
            for fn in os.listdir(config.LETHICA_DIR):
                fp = os.path.join(config.LETHICA_DIR, fn)
                if os.path.isfile(fp) and os.path.splitext(fn)[1].lower() in RAG_EXTS:
                    roots.append(fp)
            for root in roots:
                if os.path.isfile(root):
                    walk_items = [(os.path.dirname(root), [], [os.path.basename(root)])]
                else:
                    walk_items = os.walk(root)
                for rootpath, dirs, names in walk_items:
                    if dirs:
                        dirs[:] = [d for d in dirs if d not in RAG_SKIP_DIRS]
                    for fn in names:
                        fp = os.path.join(rootpath, fn)
                        if os.path.splitext(fn)[1].lower() not in RAG_EXTS:
                            continue
                        try:
                            with open(fp, "rb") as fb:
                                if b"\x00" in fb.read(1024):
                                    continue
                            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                                text = f.read()
                        except OSError:
                            continue
                        rel = os.path.relpath(fp, config.LETHICA_DIR)
                        for ci in range(0, len(text), RAG_CHUNK):
                            chunk = text[ci:ci + RAG_CHUNK]
                            if chunk.strip():
                                conn.execute("INSERT INTO idx (path, chunk_idx, text) VALUES (?,?,?)",
                                             (rel, ci // RAG_CHUNK, chunk))
                                n_chunks += 1
                        n_files += 1
            conn.commit()
            conn.close()
            return f"OK RAG rebuild: {n_files} files, {n_chunks} chunks indexed."
        if action == "stats":
            n = conn.execute("SELECT count(*) FROM idx").fetchone()[0]
            nf = conn.execute("SELECT count(DISTINCT path) FROM idx").fetchone()[0]
            conn.close()
            return f"RAG index: {nf} files, {n} chunks. DB: {RAG_DB}"
        if not query:
            return "Error rag search: butuh query."
        rows = _search_rows(conn, query)
        conn.close()
        if rows is None:
            return "Error rag search: query invalid."
        if not rows:
            return f"No RAG hits for '{query}'. Coba <rag action=\"rebuild\" /> kalau index basi."
        out = [f"RAG hits for '{query}':"]
        for path, ci, snip in rows:
            out.append(f"\n[{path}#c{ci}]\n  {snip.strip()[:250]}")
        return "\n".join(out)
    except Exception as ex:
        return f"Error rag: {ex}"


def rag_stats_summary():
    """Ringkasan index buat system prompt."""
    try:
        conn = _rag_db()
        n = conn.execute("SELECT count(*) FROM idx").fetchone()[0]
        nf = conn.execute("SELECT count(DISTINCT path) FROM idx").fetchone()[0]
        conn.close()
        if n == 0:
            return ""
        return f"{nf} files / {n} chunks terindex. Pakai <rag action=\"search\" query=\"...\" /> untuk cari."
    except Exception:
        return "(not indexed — pakai <rag action=\"rebuild\" />)"


# ── v2.7: auto-grounding (context injection per user query) ─────────
_STOPWORDS = {"yang", "untuk", "dengan", "pada", "dari", "adalah", "apa", "gimana",
              "bagaimana", "kenapa", "cara", "buat", "dan", "atau", "di", "ke", "the",
              "a", "an", "is", "are", "how", "what", "why", "to", "of", "in", "on"}


def extract_keywords(text, max_kw=6):
    """Extract kata kunci sederhana dari pertanyaan user (stopword filter + freq)."""
    words = re.findall(r"[a-zA-Z_][a-zA-Z0-9_-]{2,}", (text or "").lower())
    freq = {}
    for w in words:
        if w in _STOPWORDS or w.isdigit():
            continue
        freq[w] = freq.get(w, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:max_kw]]


def auto_ground(user_text, max_chars=1200):
    """Cari konteks relevan dari RAG index untuk pertanyaan user.
    Return string grounding block ('' kalau gak ada hit)."""
    kws = extract_keywords(user_text)
    if not kws:
        return ""
    query = " OR ".join(kws)
    try:
        conn = _rag_db()
        rows = _search_rows(conn, query, limit=6)
        conn.close()
    except Exception:
        return ""
    if not rows:
        return ""
    seen_paths, parts, total = set(), [], 0
    for path, ci, snip in rows:
        if path in seen_paths and len(seen_paths) > 2:
            continue
        seen_paths.add(path)
        chunk = f"- {path}#c{ci}: {snip.strip()[:200]}"
        if total + len(chunk) > max_chars:
            break
        parts.append(chunk)
        total += len(chunk)
    if not parts:
        return ""
    return ("\n## AUTO-CONTEXT (dari RAG index workspace — relevan dengan pertanyaan user)\n"
            + "\n".join(parts) + "\n")
