# core/cache.py — HTTP cache buat web_search/browse (SQLite, TTL, v2.8)
import json
import os
import sqlite3
import time
import urllib.error  # noqa: F401  (re-export buat caller lama)
import urllib.request

from core import config

_DB = None
_TTL = 1800  # 30 menit default


def _db():
    global _DB
    if _DB is None:
        path = os.path.join(config.LETHICA_DIR, "http-cache.db")
        _DB = sqlite3.connect(path, check_same_thread=False)
        _DB.execute("CREATE TABLE IF NOT EXISTS cache (k TEXT PRIMARY KEY, ts REAL, val TEXT)")
        _DB.execute("CREATE TABLE IF NOT EXISTS stats (k TEXT PRIMARY KEY, hits INTEGER DEFAULT 0)")
    return _DB


def get(key, ttl=_TTL):
    """Return cached value atau None. Auto-purge entry expired saat get."""
    try:
        conn = _db()
        row = conn.execute("SELECT ts, val FROM cache WHERE k=?", (key,)).fetchone()
        if not row:
            return None
        ts, val = row
        if time.time() - ts > ttl:
            conn.execute("DELETE FROM cache WHERE k=?", (key,))
            conn.commit()
            return None
        conn.execute("INSERT INTO stats (k, hits) VALUES (?,1) ON CONFLICT(k) DO UPDATE SET hits=hits+1", (key,))
        conn.commit()
        return val
    except Exception:
        return None


def put(key, val, ttl=_TTL):
    try:
        conn = _db()
        conn.execute("INSERT INTO cache (k, ts, val) VALUES (?,?,?) ON CONFLICT(k) DO UPDATE SET ts=?, val=?",
                     (key, time.time(), val, time.time(), val))
        conn.commit()
    except Exception:
        pass


def purge(ttl=_TTL):
    try:
        conn = _db()
        cur = conn.execute("DELETE FROM cache WHERE ts < ?", (time.time() - ttl,))
        conn.commit()
        return cur.rowcount
    except Exception:
        return 0


def hits_summary():
    try:
        conn = _db()
        rows = conn.execute("SELECT k, hits FROM stats ORDER BY hits DESC LIMIT 10").fetchall()
        if not rows:
            return ""
        # key format "search:<query>" → tampilkan query saja
        return "\n".join(f"  {k.split(':',1)[1][:60]}: {h} hits" for k, h in rows)
    except Exception:
        return ""


def fetch(url, ttl=_TTL, timeout=30, headers=None, method="GET", data=None):
    """HTTP GET/POST dengan SQLite cache. Return (text, from_cache)."""
    ck = f"http:{method}:{url}:{data or ''}"
    cached = get(ck, ttl)
    if cached is not None:
        return cached, True
    req = urllib.request.Request(url, data=(data.encode() if isinstance(data, str) else data),
                                 headers=headers or {"User-Agent": f"Lethica/{config.VERSION}"}, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("utf-8", errors="replace")
    put(ck, text, ttl)
    return text, False
