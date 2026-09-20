#!/data/data/com.termux/files/usr/bin/python3
"""tests/test_v371_memorydb.py — v3.7.1 memory storage SQLite (pola rag.py):
round-trip, legacy import sekali, FTS, anti-dup-id, skip-unchanged, fallback."""
import os
import sys
import json
import time
import shutil
import sqlite3
import tempfile

HOME = os.path.expanduser("~")
sys.path.insert(0, os.path.join(HOME, "lethica"))
os.chdir(os.path.join(HOME, "lethica"))

from core import memory as M  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


def fresh_memdir():
    """Dir memori baru + reset cache koneksi (test isolasi per-kasus)."""
    d = tempfile.mkdtemp(prefix="lx-v371-",
                         dir=os.path.join(HOME, "lethica", "workspace"))
    os.environ["LETHICA_MEM_DIR"] = d
    M.MEM_FILE = os.path.join(d, "memories.json")
    M.EMB_FILE = os.path.join(d, "embeddings.json")
    M.REL_FILE = os.path.join(d, "relations.json")
    M.OBS_FILE = os.path.join(d, "observability.json")
    M.close_backend()
    return d


def mk(i, body=None):
    return M.make_memory("FACT", f"t{i}", body or f"alpha beta {i} content",
                         source="USER_INPUT")


# ── 1. round-trip dasar ─────────────────────────────────────────────
d = fresh_memdir()
m = mk(1)
M.store(m, dedupe=False)
got = M.get(m["id"])
check("1.1 store→get utuh", got and got["content"] == m["content"])
check("1.2 DB dibuat, bukan JSON", os.path.isfile(M._db_path())
      and not os.path.isfile(M.MEM_FILE))
# access_count harus benar-benar tersimpan (bug get() lama)
got2 = M.get(m["id"])
check("1.3 access_count persist", got2["access_count"] == 2, str(got2["access_count"]))
upd = M.update(m["id"], {"importance": 0.9})
check("1.4 update persist", upd and M.get(m["id"])["importance"] == 0.9)

# ── 2. legacy import sekali ─────────────────────────────────────────
d2 = fresh_memdir()
legacy = [mk(10), mk(11)]
for x in legacy:
    x["id"] = f"leg{i}" if False else x["id"]
with open(M.MEM_FILE, "w") as f:
    json.dump(legacy, f)
M.close_backend()
lst = M._memories()  # trigger import
check("2.1 legacy ter-import", len(lst) == 2)
check("2.2 json di-rename .migrated", os.path.isfile(M.MEM_FILE + ".migrated"))
M.store(mk(12), dedupe=False)
check("2.3 store baru setelah import", len(M._memories()) == 3)
M.close_backend()
M._mem_db()  # reopen: tidak import ulang
check("2.4 idempotent reopen", len(M._memories()) == 3)

# ── 3. anti duplikat id (burst create-then-store) ───────────────────
d3 = fresh_memdir()
burst = [mk(i) for i in range(30)]          # dibuat semua sebelum disimpan
for b in burst:
    M.store(b, dedupe=False)
allm = M._memories()
ids = [x["id"] for x in allm]
check("3.1 30 memori tersimpan penuh", len(allm) == 30, str(len(allm)))
check("3.2 semua id unik", len(set(ids)) == 30)
check("3.3 feedback mendarat di baris benar",
      M.feedback(burst[0]["id"], "success") is not None
      and M.get(burst[0]["id"])["success_count"] == 1)

# ── 4. FTS5 prefilter ───────────────────────────────────────────────
d4 = fresh_memdir()
uniq = mk(99, body="zebraquatics unik kata langka zzz")
M.store(uniq, dedupe=False)
M.store(mk(98, body="isi lain sama sekali berbeda"), dedupe=False)
hits = M.find_ids_by_fts("zebraquatics")
check("4.1 FTS nemu kata unik", hits == [uniq["id"]], str(hits))
check("4.2 FTS input sintaks rusak -> [] (graceful)",
      M.find_ids_by_fts('AND OR "unbalanced') == [])
check("4.3 FTS kutip ganda user aman",
      M.find_ids_by_fts('zebraquatics" x') == [])

# ── 5. MAX_MEM trim ─────────────────────────────────────────────────
d5 = fresh_memdir()
_orig_cap = M.MAX_MEM
M.MAX_MEM = 60
big = [mk(i) for i in range(85)]
for b in big:
    M.store(b, dedupe=False)
check("5.1 trim ke MAX_MEM", len(M._memories()) == 60)
check("5.2 yang tersisa yang terbaru",
      M._memories()[-1]["id"] == big[-1]["id"])
M.MAX_MEM = _orig_cap

# ── 6. skip-unchanged: write ulang identik = nol churn ──────────────
d6 = fresh_memdir()
m6 = mk(60)
M.store(m6, dedupe=False)
lst6 = M._memories()
t0 = time.time()
for _ in range(10):
    M._save_memories(lst6)  # identik → semua skip
dt_skip = time.time() - t0
check("6.1 rewrite identik cepat (<10ms/call)", dt_skip / 10 < 0.01, f"{dt_skip/10*1000:.1f}ms")
# ubah satu → hanya itu yang ke-update, data utuh
lst6[0]["importance"] = 0.42
M._save_memories(lst6)
check("6.2 perubahan tetap mendarat", M.get(m6["id"])["importance"] == 0.42)

# ── 7. feedback_batch timing (regresi kontrak v3.6.1: <0.45s/80 id) ──
d7 = fresh_memdir()
mems7 = [mk(i) for i in range(90)]
for x in mems7:
    M.store(x, dedupe=False)
ids7 = [x["id"] for x in mems7]
t0 = time.time()
for _ in range(3):
    M.feedback_batch(ids7[:80], "success")
dt = time.time() - t0
check("7.1 3x feedback_batch 80id < 0.45s", dt < 0.45, f"{dt:.3f}s")
check("7.2 success_count akurat", M.get(ids7[0])["success_count"] == 3)

# ── 8. konsistensi urutan & snapshot isolation ──────────────────────
d8 = fresh_memdir()
a, b = mk(80), mk(81)
M.store(a, dedupe=False)
snap = M._memories()
M.store(b, dedupe=False)
check("8.1 snapshot lama tidak berubah", len(snap) == 1 and len(M._memories()) == 2)
check("8.2 urutan store dipertahankan",
      [x["id"] for x in M._memories()] == [a["id"], b["id"]])

# ── 9. fallback JSON kalau DB unwritable ────────────────────────────
d9 = fresh_memdir()
m9 = mk(90)
M.store(m9, dedupe=False)
# rusak DB secara manual lalu paksa _memories jatuh ke JSON lama
body = json.dumps([m9], ensure_ascii=False)
with open(M.MEM_FILE, "w") as f:
    f.write(body)
os.remove(M._db_path())
M.close_backend()
conn = sqlite3.connect(M._db_path())
conn.execute("CREATE TABLE memories(broken TEXT)")
conn.commit()
conn.close()
mems9 = M._memories()  # DB error → fallback
check("9.1 DB korup → fallback JSON", len(mems9) == 1 and mems9[0]["id"] == m9["id"],
      str([x.get("id") for x in mems9]))
M.close_backend()

# ── 10. link() regression bug lama (save in-place) ──────────────────
dA = fresh_memdir()
p1, p2 = mk(100), mk(101)
M.store(p1, dedupe=False)
M.store(p2, dedupe=False)
M.link(p1["id"], p2["id"], "RELATED")
got1 = M.get(p1["id"])
check("10.1 related_memories persist",
      p2["id"] in got1.get("related_memories", []), str(got1.get("related_memories")))

for d in (d, d2, d3, d4, d5, d6, d7, d8, d9, dA):
    shutil.rmtree(d, ignore_errors=True)
M.close_backend()

print(f"\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", ", ".join(FAIL))
    sys.exit(1)
