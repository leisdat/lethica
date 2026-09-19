# core/memory.py — v3.5.0 Semantic Long-Term Memory
#
# Evolusi dari lexical recall (v3.1 experience.recall) menjadi:
#   SEMANTIC + STRUCTURED + LONG-TERM MEMORY
#
# Prinsip (dari mission):
#   - TIDAK rebuild Lethica. Reuse storage/helper existing (experience.py, config.py).
#   - TIDAK hapus Experience Memory. experience.* tetap jalan & dipanggil berdampingan.
#   - TIDAK introduce infra berat. Storage = JSON lokal (memory/memories.json).
#   - Embedding OPTIONAL. Default OFF → semantic_search fallback ke lexical.
#   - Deterministic fallback selalu ada.
#
# Arsitektur ringkas:
#   SHORT-TERM (current Task Memory via experience.py)
#        + LONG-TERM (semantic Memory store di sini)
#        + STRUCTURED (Facts/Relations/Project/Solution/Lesson)
#        -> MEMORY RETRIEVER (hybrid_search)
#        -> RELEVANCE RANKER (MemoryScore + reasons)
#        -> CONTEXT BUILDER (context budget)
#        -> PLANNER (orchestra.py, non-breaking)
import os
import re
import json
import time
import math
import hashlib
from collections import defaultdict
from datetime import datetime, timezone

from core import config
from core import experience  # reuse helpers
from core.experience import _norm, _tags, _jaccard, _ts  # reuse lexical utils

# MEMORY_DIR bisa di-redirect via env LETHICA_MEM_DIR (test isolation, sejajar
# dengan LETHICA_GRAPH_DIR di graph.py). Tanpa env = config.MEMORY_DIR default.
MEM_FILE = os.path.join(os.environ.get("LETHICA_MEM_DIR") or config.MEMORY_DIR, "memories.json")
EMB_FILE = os.path.join(os.environ.get("LETHICA_MEM_DIR") or config.MEMORY_DIR, "embeddings.json")
REL_FILE = os.path.join(os.environ.get("LETHICA_MEM_DIR") or config.MEMORY_DIR, "relations.json")
OBS_FILE = os.path.join(os.environ.get("LETHICA_MEM_DIR") or config.MEMORY_DIR, "observability.json")

MEMORY_TYPES = {
    "TASK", "FAILURE", "SOLUTION", "SKILL", "STRATEGY", "PROJECT",
    "KNOWLEDGE", "FACT", "PREFERENCE", "DECISION", "LESSON", "EXPERIENCE",
}
SCOPES = {"GLOBAL", "PROJECT", "TASK", "SKILL", "STRATEGY"}
SOURCES = {"LETHICA_INFERENCE", "WEB_EVIDENCE", "EXECUTION_EVIDENCE", "USER_INPUT"}
CONF_LEVELS = {"LOW", "MEDIUM", "HIGH"}

MAX_MEM = 2000          # cap store supaya json gak bengkak
CONTEXT_MAX_ITEMS = 10
CONTEXT_MAX_TOKENS = 4000

# ── secret redaction (Phase 22) ──────────────────────────────────────
_SECRET_RE = re.compile(
    r"(?i)(sk-[a-z0-9]{8,}|gsk_[a-z0-9_-]{8,}|Bearer\s+[a-z0-9._-]{16,}|"
    r"api[_-]?key[\"'\s:=]+[a-z0-9_\-]{12,}|"
    r"token[\"'\s:=]+[a-z0-9._-]{16,}|"
    r"pd[Kk][A-Za-z0-9]{20,}|thk_live_[A-Za-z0-9_-]{10,})"
)


def redact(text):
    """REDACT raw secrets sebelum persist. Gak simpan secret mentah."""
    if not isinstance(text, str):
        return text
    return _SECRET_RE.sub("[REDACTED:secret]", text)


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ts(iso):
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").timestamp()
    except Exception:
        return 0.0


# ── observability (Phase 31) ────────────────────────────────────────
_OBS_DEFAULT = {
    "memory_stores": 0, "memory_reads": 0, "semantic_queries": 0,
    "lexical_queries": 0, "hybrid_queries": 0, "cache_hits": 0, "cache_misses": 0,
    "retrieval_latency_ms": 0, "embedding_latency_ms": 0, "ranking_latency_ms": 0,
    "memory_used": 0, "memory_helpful": 0, "memory_harmful": 0,
    "memory_conflicts": 0, "memory_consolidations": 0, "memory_archived": 0,
}


def _load_obs():
    try:
        with open(OBS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        for k, v in _OBS_DEFAULT.items():
            d.setdefault(k, v)
        return d
    except Exception:
        return dict(_OBS_DEFAULT)


def _save_obs(d):
    try:
        tmp = OBS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f)
        os.replace(tmp, OBS_FILE)
    except Exception:
        pass


def obs_inc(*keys, amount=1):
    d = _load_obs()
    for k in keys:
        if k in d:
            d[k] += amount
    _save_obs(d)


def observability():
    return _load_obs()


# ── storage (reuse pattern dari experience.py) ──────────────────────
def _load(path, default):
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return default
    return default


def _save(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def _memories():
    return _load(MEM_FILE, [])


def _save_memories(lst):
    _save(MEM_FILE, lst[-MAX_MEM:])


def _relations():
    return _load(REL_FILE, [])


# ── unified memory model (Phase 1) ──────────────────────────────────
def make_memory(
    type, title, content, summary=None, tags=None, entities=None,
    project_id=None, task_id=None, skill_id=None, strategy_id=None,
    source="LETHICA_INFERENCE", scope="GLOBAL", confidence="LOW",
    importance=0.5, metadata=None,
):
    """Buat record memori terstandarisasi. Field gak wajib terisi semua."""
    if type not in MEMORY_TYPES:
        raise ValueError(f"invalid memory type: {type}")
    if scope not in SCOPES:
        raise ValueError(f"invalid scope: {scope}")
    if source not in SOURCES:
        raise ValueError(f"invalid source: {source}")
    tags = tags or []
    entities = entities or []
    now = _now()
    mid = f"m{int(time.time()*1000)}-{len(_memories())}"
    return {
        "id": mid,
        "type": type,
        "title": redact(title or content[:60]),
        "content": redact(content or ""),
        "summary": redact(summary or (content or "")[:200]),
        "tags": sorted(set(_tags(title + " " + content) + list(tags)))[:20],
        "entities": entities[:20],
        "project_id": project_id,
        "task_id": task_id,
        "skill_id": skill_id,
        "strategy_id": strategy_id,
        "source": source,
        "scope": scope,
        "timestamp": now,
        "importance": float(importance),
        "confidence": confidence if confidence in CONF_LEVELS else "LOW",
        "confidence_score": {"LOW": 0.3, "MEDIUM": 0.6, "HIGH": 0.9}[confidence] if confidence in CONF_LEVELS else 0.3,
        "access_count": 0,
        "success_count": 0,
        "failure_count": 0,
        "last_accessed": now,
        "related_memories": [],
        "metadata": metadata or {},
        # v3.5 extra signals
        "version_ref": (metadata or {}).get("version"),
        "quality": "UNVERIFIED",
        "archived": False,
        "consolidated_from": [],
    }


# ── lifecycle: CAPTURE → NORMALIZE → VALIDATE → DEDUPLICATE → STORE (Phase 2) ──
def _classify_confidence(m):
    """Confidence dari evidence (Phase 15), bukan dari diulang model."""
    if m["source"] == "EXECUTION_EVIDENCE" and m.get("success_count", 0) >= 3:
        return "HIGH", 0.9
    if m["source"] == "EXECUTION_EVIDENCE":
        return "MEDIUM", 0.6
    if m["source"] == "USER_INPUT":
        return "MEDIUM", 0.6
    if m["source"] == "WEB_EVIDENCE":
        return "MEDIUM", 0.55
    # LETHICA_INFERENCE = model output, default rendah
    return "LOW", 0.3


def _dedupe_key(m):
    base = (m["type"] + "|" + (m.get("project_id") or "") + "|" + _norm(m["content"])[:120])
    return hashlib.md5(base.encode()).hexdigest()


def _find_dup(m, store):
    """Deteksi duplikat: exact normalized / sama project+problem+solution."""
    dk = _dedupe_key(m)
    for ex in store:
        if ex.get("_dk") == dk:
            return ex
        # same project + same normalized content
        if (ex.get("project_id") == m.get("project_id")
                and _norm(ex["content"])[:120] == _norm(m["content"])[:120]
                and ex["type"] == m["type"]):
            return ex
    return None


def store(memory, dedupe=True):
    """Simpan memori. Jalankan normalize→validate→dedupe→store→index."""
    if not isinstance(memory, dict) or "type" not in memory:
        raise ValueError("store: memory dict with 'type' required")
    # normalize fields
    memory["content"] = redact(memory.get("content", ""))
    memory["title"] = redact(memory.get("title", "") or memory["content"][:60])
    if not memory.get("tags"):
        memory["tags"] = sorted(set(_tags(memory["title"] + " " + memory["content"])))[:20]
    memory["_dk"] = _dedupe_key(memory)
    store_list = _memories()

    if dedupe:
        dup = _find_dup(memory, store_list)
        if dup:
            # merge carefully: preserve both sources (Phase 14)
            if memory["id"] not in dup.get("consolidated_from", []):
                dup.setdefault("consolidated_from", []).append(memory["id"])
                dup["access_count"] = dup.get("access_count", 0) + 1
                # bump confidence kalau ada bukti eksekusi baru
                if memory.get("source") == "EXECUTION_EVIDENCE":
                    dup["success_count"] = dup.get("success_count", 0) + 1
                    if dup["success_count"] >= 3:
                        dup["quality"] = "REUSABLE"
            _save_memories(store_list)
            obs_inc("memory_stores")
            return dup

    conf, cscore = _classify_confidence(memory)
    memory["confidence"] = conf
    memory["confidence_score"] = cscore
    memory["quality"] = "CONFIRMED" if memory.get("source") == "EXECUTION_EVIDENCE" else "UNVERIFIED"
    store_list.append(memory)
    _save_memories(store_list)
    obs_inc("memory_stores")
    return memory


# ── lexical retrieval (reuse experience helpers) ────────────────────
def _lexical_sim(qnorm, m):
    qtags = set(_tags(qnorm))
    mnorm = _norm(m.get("content", "") or m.get("title", ""))
    sim = _jaccard(qnorm, mnorm)
    if qtags and m.get("tags"):
        mtags = set(m["tags"])
        overlap = len(qtags & mtags)
        if overlap:
            sim = min(1.0, sim + 0.08 * overlap)
    return sim


# ── embedding provider abstraction (Phase 5) — OPTIONAL, default off ──
class EmbeddingProvider:
    def embed(self, text): raise NotImplementedError
    def embed_batch(self, texts): return [self.embed(t) for t in texts]
    def dimensions(self): raise NotImplementedError
    def model_name(self): return "none"
    def health_check(self): return False


class NullEmbeddingProvider(EmbeddingProvider):
    """Default: gak ada embedding. semantic_search fallback ke lexical."""
    def model_name(self): return "null"
    def health_check(self): return False


class RouterkuEmbeddingProvider(EmbeddingProvider):
    """Optional: pakai routerku /v1/embeddings kalau provider support.
    Diaktifkan via config [memory.semantic] enabled=true provider=routerku."""
    def __init__(self, base, key, model="text-embedding-3-small"):
        self.base = base.rstrip("/")
        self.key = key
        self.model = model
        self._dims = None

    def embed(self, text):
        import urllib.request
        body = json.dumps({"model": self.model, "input": text[:8000]}).encode()
        req = urllib.request.Request(
            self.base + "/embeddings",
            data=body,
            headers={"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            d = json.load(r)
        vec = d["data"][0]["embedding"]
        self._dims = len(vec)
        return vec

    def dimensions(self): return self._dims or 0
    def model_name(self): return self.model
    def health_check(self):
        try:
            return bool(self.embed("ping"))
        except Exception:
            return False


def _get_provider():
    """Baca config [memory.semantic]; default NullProvider."""
    cfg = config.CFG.get("memory", {}).get("semantic", {})
    if not cfg.get("enabled"):
        return NullEmbeddingProvider()
    prov = cfg.get("provider", "routerku")
    if prov == "routerku":
        p = config.providers().get("routerku", {})
        return RouterkuEmbeddingProvider(p.get("base", "http://127.0.0.1:20130/v1"), p.get("key", ""), cfg.get("model", "text-embedding-3-small"))
    return NullEmbeddingProvider()


def _cosine(a, b):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


# ── semantic retrieval (Phase 4) — fallback lexical kalau gak ada provider
_EMB_CACHE = None


def _embeddings_cache():
    global _EMB_CACHE
    if _EMB_CACHE is None:
        _EMB_CACHE = _load(EMB_FILE, {})
    return _EMB_CACHE


def semantic_search(query, top_k=8, project_id=None, scope=None):
    """Embedding-based retrieval. Kalau provider null → return [] (caller fallback lexical)."""
    obs_inc("semantic_queries")
    prov = _get_provider()
    if not prov.health_check():
        return []  # signal: fallback ke lexical
    try:
        t0 = time.time()
        qvec = prov.embed(query)
        obs_inc("embedding_latency_ms", amount=int((time.time() - t0) * 1000))
    except Exception:
        return []
    cache = _embeddings_cache()
    results = []
    for m in _memories():
        if m.get("archived"):
            continue
        if project_id and m.get("project_id") and m["project_id"] != project_id:
            if m.get("scope") != "GLOBAL":
                continue
        vec = cache.get(m["id"])
        if vec is None:
            try:
                vec = prov.embed(m.get("content", "") or m.get("title", ""))
                cache[m["id"]] = vec
            except Exception:
                continue
        sim = _cosine(qvec, vec)
        results.append((sim, m))
    results.sort(key=lambda x: -x[0])
    # persist cache
    _save(EMB_FILE, cache)
    return [{"memory_id": m["id"], "semantic_sim": round(s, 3), "memory": m} for s, m in results[:top_k]]


# ── hybrid retrieval (Phase 7) + relevance ranker (Phase 8) ──────────
def _recency_score(m):
    age_days = (time.time() - _ts(m.get("timestamp"))) / 86400
    # 1.0 (baru) → 0.2 (tua 60+ hari), tapi gak pernah 0 (historical preserved)
    return max(0.2, 1.0 - age_days / 75.0)


def _importance_score(m):
    return float(m.get("importance", 0.5))


def _success_score(m):
    s, f = m.get("success_count", 0), m.get("failure_count", 0)
    total = s + f
    if total == 0:
        return 0.5
    return s / total


def _metadata_match(m, ctx):
    """Project/skill/strategy/task match terhadap context (Phase 9)."""
    score = 0.0
    reasons = []
    has_query_signal = False  # hanya beri global baseline kalau ada relevansi lex/sem
    if ctx.get("project_id") and m.get("project_id"):
        if m["project_id"] == ctx["project_id"]:
            score += 1.0
            reasons.append("same_project")
        elif m.get("scope") == "GLOBAL":
            score += 0.4
            reasons.append("global_scope_cross_project")
    elif m.get("scope") == "GLOBAL":
        # global baseline HANYA kalau query punya sinyal (hindari false boost utk query tak terkait)
        if ctx.get("_has_signal"):
            score += 0.5
    if ctx.get("skill_id") and m.get("skill_id") == ctx["skill_id"]:
        score += 0.6
        reasons.append("same_skill")
    if ctx.get("strategy_id") and m.get("strategy_id") == ctx["strategy_id"]:
        score += 0.5
        reasons.append("same_strategy")
    if ctx.get("task_id") and m.get("task_id") == ctx["task_id"]:
        score += 0.4
        reasons.append("same_task")
    return min(1.0, score), reasons


def rank_memory(memory, query_norm, semantic_sim, ctx):
    """Return MemoryScore: relevance, confidence, evidence, reasons[]."""
    reasons = []
    lex = _lexical_sim(query_norm, memory)
    rec = _recency_score(memory)
    imp = _importance_score(memory)
    suc = _success_score(memory)
    meta, meta_reasons = _metadata_match(memory, ctx)
    reasons += meta_reasons

    # weighted hybrid (Phase 7): semantic+lexical+metadata+recency+importance+success - irrelevance
    w = {
        "lex": 0.25, "sem": 0.20, "meta": 0.35,
        "rec": 0.08, "imp": 0.07, "suc": 0.05,
    }
    relevance = (
        w["lex"] * lex
        + w["sem"] * (semantic_sim if semantic_sim is not None else 0.0)
        + w["meta"] * meta
        + w["rec"] * rec
        + w["imp"] * imp
        + w["suc"] * suc
    )
    # strong project/skill match MUST dominate lexical noise (Phase 9/35)
    if meta >= 1.0:
        relevance = max(relevance, 0.65)
        reasons.append("project_match_floor")
    # penalty: contradiction / low quality
    irr = 0.0
    if memory.get("quality") == "UNVERIFIED" and memory.get("source") == "LETHICA_INFERENCE":
        irr += 0.05
        reasons.append("inference_unverified_penalty")
    relevance = max(0.0, min(1.0, relevance - irr))

    # confidence: gabungan model confidence + evidence
    conf_raw = memory.get("confidence_score", 0.3)
    evidence = f"src={memory.get('source')} succ={memory.get('success_count',0)} fail={memory.get('failure_count',0)} q={memory.get('quality')}"
    if lex >= 0.55:
        reasons.append(f"lexical_high({lex:.2f})")
    if semantic_sim and semantic_sim >= 0.8:
        reasons.append(f"semantic_high({semantic_sim:.2f})")
    if meta >= 1.0:
        reasons.append("strong_metadata_match")
    return {
        "memory_id": memory["id"],
        "relevance": round(relevance, 4),
        "confidence": round((conf_raw + suc * 0.1) / 1.1, 3),
        "evidence": evidence,
        "reasons": reasons,
        "lexical_sim": round(lex, 3),
        "semantic_sim": round(semantic_sim, 3) if semantic_sim is not None else None,
        "memory": memory,
    }


def hybrid_search(query, top_k=8, ctx=None, max_items=None, max_tokens=CONTEXT_MAX_TOKENS):
    """HYBRID SEARCH: semantic(+fallback lexical) + lexical + metadata + recency + importance + success."""
    obs_inc("hybrid_queries")
    ctx = ctx or {}
    qnorm = _norm(query)
    t0 = time.time()
    obs_inc("memory_reads")

    # semantic (bisa kosong kalau gak ada provider → fallback)
    sem = semantic_search(query, top_k=top_k * 2, project_id=ctx.get("project_id"))
    sem_map = {r["memory_id"]: r["semantic_sim"] for r in sem}
    if not sem:
        obs_inc("lexical_queries")  # fallback path

    scored = []
    for m in _memories():
        if m.get("archived"):
            continue
        if ctx.get("project_id") and m.get("project_id") and m["project_id"] != ctx["project_id"] and m.get("scope") != "GLOBAL":
            continue
        ssim = sem_map.get(m["id"])
        # signal: ada lexical atau semantic overlap → global memory berhak dapat baseline boost
        lex_preview = _lexical_sim(qnorm, m)
        has_signal = (lex_preview > 0) or (ssim is not None and ssim > 0)
        ctx_sig = dict(ctx, _has_signal=has_signal)
        sc = rank_memory(m, qnorm, ssim, ctx_sig)
        scored.append(sc)

    scored.sort(key=lambda x: (-x["relevance"], -x["memory"].get("confidence_score", 0.3)))
    obs_inc("ranking_latency_ms", amount=int((time.time() - t0) * 1000))

    # context budget (Phase 25) — only applied if max_items given (retrieve_for_plan passes it)
    if max_items is None:
        return scored
    out, toks = [], 0
    for sc in scored:
        est = len(sc["memory"].get("content", "")) // 4 + 50
        if len(out) >= max_items or toks + est > max_tokens:
            break
        out.append(sc)
        toks += est
    return out


# ── compat retrieval buat planner (Phase 26) — shape mirip experience.recall ──
def retrieve_for_plan(goal, project_id=None, skill_id=None, strategy_id=None, task_id=None, top_k=5, **kwargs):
    """Dipanggil orchestra bersama experience.recall. Return dict kompatibel
    plus field 'memories' (rich v3.5). TIDAK break existing planner."""
    ctx = {"project_id": project_id, "skill_id": skill_id, "strategy_id": strategy_id, "task_id": task_id}
    ranked = hybrid_search(goal, top_k=top_k, ctx=ctx, **kwargs)
    similar = []
    for sc in ranked:
        m = sc["memory"]
        similar.append({
            "memory_id": m["id"],
            "type": m["type"],
            "similarity": sc["lexical_sim"] or (sc["semantic_sim"] or 0.0),
            "relevance": sc["relevance"],
            "title": m.get("title", "")[:100],
            "result": m.get("quality", "?"),
            "content": m.get("content", "")[:300],
            "reasons": sc["reasons"],
        })
    return {
        "similar_tasks": similar,           # kompatibel dgn experience.recall shape
        "memories": [sc["memory"] for sc in ranked],  # rich v3.5
        "scores": [{k: sc[k] for k in ("memory_id", "relevance", "confidence", "evidence", "reasons")} for sc in ranked],
    }


# ── get / update / link / archive / feedback / conflict (Phase 29) ──
def get(memory_id):
    for m in _memories():
        if m["id"] == memory_id:
            m["access_count"] = m.get("access_count", 0) + 1
            m["last_accessed"] = _now()
            _save_memories(_memories())
            return m
    return None


def update(memory_id, patch):
    lst = _memories()
    for m in lst:
        if m["id"] == memory_id:
            for k, v in patch.items():
                if k in ("content", "title", "summary"):
                    m[k] = redact(v)
                else:
                    m[k] = v
            m["updated_at"] = _now()
            _save_memories(lst)
            return m
    return None


def link(a_id, b_id, relation):
    """Lightweight relation layer (Phase 30). Gak butuh graph DB."""
    rels = _relations()
    rels.append({"from": a_id, "to": b_id, "relation": relation, "ts": _now()})
    _save(REL_FILE, rels[-500:])
    # juga catat di memory.related_memories
    lst = _memories()
    for m in lst:
        if m["id"] == a_id and b_id not in m.get("related_memories", []):
            m.setdefault("related_memories", []).append(b_id)
        if m["id"] == b_id and a_id not in m.get("related_memories", []):
            m.setdefault("related_memories", []).append(a_id)
    _save_memories(lst)
    return True


def archive(memory_id):
    m = update(memory_id, {"archived": True})
    if m:
        obs_inc("memory_archived")
    return m


def feedback(memory_id, outcome, helpful=None):
    """Phase 16: memory dipakai → record evidence. outcome: success|failure."""
    lst = _memories()
    for m in lst:
        if m["id"] == memory_id:
            if outcome == "success":
                m["success_count"] = m.get("success_count", 0) + 1
                if m["success_count"] >= 2 and m.get("source") == "EXECUTION_EVIDENCE":
                    m["quality"] = "REUSABLE"
                m["confidence_score"] = min(1.0, m.get("confidence_score", 0.3) + 0.1)
            else:
                m["failure_count"] = m.get("failure_count", 0) + 1
                m["confidence_score"] = max(0.1, m.get("confidence_score", 0.3) - 0.2)
                if m["failure_count"] >= 2:
                    m["quality"] = "UNVERIFIED"
            m["last_accessed"] = _now()
            _save_memories(lst)
            obs_inc("memory_used")
            obs_inc("memory_helpful" if (helpful is True or outcome == "success") else "memory_harmful")
            return m
    return None


def feedback_batch(memory_ids, outcome, helpful=None):
    """Bulk feedback (Phase 16) — SATU tulis untuk N id. feedback() per-id
    menulis ulang memories.json tiap iterasi; di Termux I/O itu mahal (80+ hit
    → detik). Perilaku per-id identik dengan feedback(); return jumlah di-proses."""
    ids = [i for i in (memory_ids or []) if i]
    if not ids:
        return 0
    lst = _memories()
    touched = 0
    want = set(ids[:300])          # sanity cap; sisanya diabaikan (bukan error)
    for m in lst:
        if m["id"] not in want:
            continue
        if outcome == "success":
            m["success_count"] = m.get("success_count", 0) + 1
            if m["success_count"] >= 2 and m.get("source") == "EXECUTION_EVIDENCE":
                m["quality"] = "REUSABLE"
            m["confidence_score"] = min(1.0, m.get("confidence_score", 0.3) + 0.1)
        else:
            m["failure_count"] = m.get("failure_count", 0) + 1
            m["confidence_score"] = max(0.1, m.get("confidence_score", 0.3) - 0.2)
            if m["failure_count"] >= 2:
                m["quality"] = "UNVERIFIED"
        m["last_accessed"] = _now()
        touched += 1
    if touched:
        _save_memories(lst)
        obs_inc("memory_used", amount=touched)
        obs_inc("memory_helpful" if (helpful is True or outcome == "success") else "memory_harmful",
                amount=touched)
    return touched


# ── consolidation (Phase 13) + decay (Phase 17) + conflict (Phase 18) ──
def consolidate():
    """Gabungkan memori berulang jadi 1 Known Solution, preserve sources."""
    lst = _memories()
    groups = defaultdict(list)
    for m in lst:
        if m.get("archived"):
            continue
        if m["type"] in ("SOLUTION", "FACT", "LESSON"):
            groups[_dedupe_key(m)].append(m)
    merged = 0
    for dk, items in groups.items():
        if len(items) < 2:
            continue
        items.sort(key=lambda x: x.get("success_count", 0), reverse=True)
        primary = items[0]
        sources = []
        for it in items[1:]:
            sources.append(it["id"])
            it["archived"] = True
        primary.setdefault("consolidated_from", []).extend(sources)
        primary["consolidated_from"] = list(set(primary["consolidated_from"]))
        if len(items) >= 3:
            primary["quality"] = "REUSABLE"
            primary["importance"] = min(1.0, primary.get("importance", 0.5) + 0.1)
        merged += 1
    _save_memories(lst)
    obs_inc("memory_consolidations", amount=merged)
    return merged


def decay():
    """Controlled decay: turunkan relevance lewat importance, arsip kalau sangat tua+low reuse.
    TIDAK hapus historical evidence (Phase 17)."""
    lst = _memories()
    changed = 0
    for m in lst:
        if m.get("archived"):
            continue
        age_days = (time.time() - _ts(m.get("timestamp"))) / 86400
        reuse = m.get("access_count", 0) + m.get("success_count", 0)
        # decay importance perlahan kalau tua & jarang dipakai
        if age_days > 60 and reuse == 0:
            new_imp = max(0.1, m.get("importance", 0.5) - 0.05)
            if new_imp != m.get("importance"):
                m["importance"] = round(new_imp, 2)
                changed += 1
        # auto-archive kalau sangat tua, low importance, gak ada success
        if age_days > 120 and m.get("importance", 0.5) <= 0.15 and m.get("success_count", 0) == 0:
            m["archived"] = True
            obs_inc("memory_archived")
            changed += 1
    if changed:
        _save_memories(lst)
    return changed


def detect_conflict():
    """Phase 18: cari memori kontradiktif (same entity/field, nilai beda)."""
    lst = _memories()
    conflicts = []
    by_entity = defaultdict(list)
    for m in lst:
        for e in m.get("entities", []):
            by_entity[e].append(m)
    for ent, items in by_entity.items():
        if len(items) < 2:
            continue
        # bandingkan normalized content; kalau beda & gak subset → conflict
        norms = {i["id"]: _norm(i["content"]) for i in items}
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = norms[items[i]["id"]], norms[items[j]["id"]]
                if a and b and a != b and not (a in b or b in a):
                    conflicts.append({
                        "entity": ent,
                        "a": items[i]["id"], "b": items[j]["id"],
                        "a_content": items[i]["content"][:120],
                        "b_content": items[j]["content"][:120],
                        "a_ts": items[i].get("timestamp"),
                        "b_ts": items[j].get("timestamp"),
                        "note": "CONFLICT — newest not automatically correct",
                    })
    obs_inc("memory_conflicts", amount=len(conflicts))
    return conflicts


# ── extraction helper (Phase 3): dari task → memori terstruktur ──────
def extract_from_task(task):
    """Ambil task selesai → simpan TASK + (kalau sukses) SOLUTION + LESSON.
    Gak simpan transcript utuh. Compact & useful."""
    goal = getattr(task, "goal", "") or ""
    result = "success" if getattr(task, "state", "") == "COMPLETED" else "failure"
    project_id = getattr(task, "project_id", None)
    skill_id = (getattr(task, "skill_report", {}) or {}).get("active_skill")
    out = []
    # TASK memory
    out.append(store(make_memory(
        type="TASK", title=goal[:80], content=goal,
        project_id=project_id, task_id=task.id, skill_id=skill_id,
        source="EXECUTION_EVIDENCE" if result == "success" else "LETHICA_INFERENCE",
        scope="PROJECT" if project_id else "GLOBAL",
        importance=0.5,
    )))
    if result == "success":
        sol = getattr(task, "final_solution", "") or (getattr(task, "critic", {}) or {}).get("requirements_met", [""])[0]
        if sol:
            out.append(store(make_memory(
                type="SOLUTION", title=f"sol: {goal[:60]}", content=sol[:600],
                project_id=project_id, task_id=task.id, skill_id=skill_id,
                source="EXECUTION_EVIDENCE", scope="PROJECT" if project_id else "GLOBAL",
                importance=0.7, metadata={"evidence": "1 successful execution"},
            )))
    # LESSON dari debug_log (root_cause → lesson)
    for d in getattr(task, "debug_log", []) or []:
        rc = d.get("root_cause")
        if rc:
            out.append(store(make_memory(
                type="LESSON", title=f"lesson: {rc[:60]}",
                content=f"{rc}. Fix: {d.get('fix_steps', '')}",
                project_id=project_id, source="EXECUTION_EVIDENCE",
                scope="GLOBAL", importance=0.6,
            )))
    return out


# ── summary for system prompt ───────────────────────────────────────
def summary():
    lst = _memories()
    by_type = defaultdict(int)
    for m in lst:
        by_type[m["type"]] += 1
    active = [m for m in lst if not m.get("archived")]
    return (f"Semantic Memory v3.5: {len(lst)} total ({len(active)} active). "
            + " · ".join(f"{k}={v}" for k, v in sorted(by_type.items())))


if __name__ == "__main__":
    print(summary())
