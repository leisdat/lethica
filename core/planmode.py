# core/planmode.py — Plan mode: agent bikin rencana → user approve → baru eksekusi.
# Dipakai TUI (core/loop.py, approval via Confirm) & Telegram bridge
# (lethica_bridge.py, approval via chat "gas"/revisi/"batal").
import re

from core import config, client as client_mod, tools

# kata user = setuju / batal (cek substring, case-insensitive)
APPROVE_WORDS = ("gas", "gaskeun", "gass", "ok", "oke", "lanjut", "lanjutkan",
                 "setuju", "yes", "y", "go", "eksekusi", "jalan", "jalankan",
                 "sip", "deal", "acc", "laksanakan", "boleh", "yuk")
REJECT_WORDS = ("batal", "batalkan", "cancel", "gak jadi", "nggak jadi",
                "tidak jadi", "jangan", "stop", "berhenti", "no", "n")

# kata kerja aksi (id + en) → heuristik "ini task, bukan obrolan"
_TASK_VERBS = (
    "buatkan", "buat", "bikin", "bikinin", "perbaiki", "benerin", "tambah",
    "tambahkan", "cari", "carikan", "analisis", "analisa", "cek", "tolong",
    "jalankan", "tulis", "tuliskan", "refactor", "debug", "test", "tes",
    "deploy", "install", "update", "upgrade", "hapus", "ganti", "ubah",
    "setup", "config", "konfigur", "riset", "research", "bandingkan",
    "rangkum", "implement", "kembangin", "optimal", "scan", "audit",
    "migrasi", "generate",
)


def mode():
    """PLAN_MODE dari config: off | auto | always. Default auto."""
    return (getattr(config, "PLAN_MODE", "auto") or "auto").lower()


def is_task_like(text):
    """Heuristik murah: apakah pesan user terlihat seperti task kerja."""
    t = (text or "").strip().lower()
    if len(t) < 12:
        return False
    if t.startswith(("/", "!", ".")):
        return False  # command
    # pertanyaan pendek tanpa kata kerja aksi → bukan task
    if t.endswith("?") and len(t) < 90 and not any(v in t for v in _TASK_VERBS):
        return False
    if any(v in t for v in _TASK_VERBS):
        return True
    return len(t) > 160  # pesan panjang tanpa kata kerja → anggap task/diskusi kerja


def should_draft(user_text, plan_approved=False):
    """Perlu bikin plan dulu sebelum eksekusi?"""
    m = mode()
    if m == "off" or plan_approved:
        return False
    if m == "always":
        return True
    return is_task_like(user_text)  # auto


def check_approval(text):
    """Klasifikasi balasan user terhadap plan pending: approve|reject|revise."""
    t = (text or "").strip().lower()
    if not t:
        return "revise"
    # reject dulu (mis. "gak jadi" mengandung "jadi" tapi bukan approve)
    if any(w in t for w in REJECT_WORDS):
        # "no" / "n" satu huruf rawan false-positive → hanya kalau pendek
        if re.fullmatch(r"(no|n|batal|cancel|stop)", t) or any(
                w in t for w in ("batal", "cancel", "gak jadi", "nggak jadi",
                                "tidak jadi", "jangan", "berhenti")):
            return "reject"
    if any(w in t for w in APPROVE_WORDS):
        # hindari "y" nyasar di kata lain → approve word harus berdiri sendiri
        # atau pesan pendek
        words = set(re.findall(r"[a-z]+", t))
        if words & set(APPROVE_WORDS) or len(t) <= 12:
            return "approve"
    return "revise"


def draft_plan(user_text, model=None, client=None, context=""):
    """Satu panggilan LLM → rencana langkah bernomor. Simpan via tool_plan.
    Return (plan_text, used_model). Tidak mutasi messages caller.
    v3.8.1: retry 2x kalau respons kosong (model lagi flaky). Kalau tetap
    gagal → return (None, used): caller harus SKIP plan gate dan eksekusi
    langsung (jangan sodorkan "(empty reply)" ke user)."""
    cl = client or client_mod.LClient()
    model = model or config.DEFAULT_MODEL
    sys = ("Kamu perencana task untuk AI agent. Buatkan RENCANA KERJA bernomor "
           "untuk goal user di bawah. Aturan:\n"
           "- Maks 8 langkah, tiap langkah 1 baris: apa yang dilakukan + tool yang dipakai.\n"
           "- Tandai langkah yang BISA PARALEL dengan [PARALEL].\n"
           "- Jangan eksekusi, jangan panggil tool — hanya rencana.\n"
           "- Bahasa Indonesia, ringkas, to-the-point.")
    msgs = [{"role": "system", "content": sys},
            {"role": "user",
             "content": f"GOAL:\n{user_text}\n\n{f'KONTEKS TAMBAHAN:\n{context}' if context else ''}"}]
    reply, used = None, None
    for _ in range(3):
        try:
            reply, used = cl.chat_failover(
                model, msgs, config.FAILOVER_CHAIN,
                timeout=min(config.HTTP_TIMEOUT, 90), temperature=0.3, max_tokens=1200)
        except Exception:
            reply, used = None, used
        plan_text = (reply or "").strip()
        if plan_text and plan_text != "(empty reply)":
            break
    else:
        plan_text = ""
    if not plan_text:
        return None, used  # draft gagal total → caller skip plan gate
    try:
        tools.tool_plan("save", f"Goal: {user_text[:200]}\n\n{plan_text}")
    except Exception:
        pass
    return plan_text, used


def approval_message(plan_text):
    return (f"Plan berikut DISETUJUI user. Eksekusi langkah demi langkah SEKARANG, "
            f"update progress via <plan action=\"append\" ... /> tiap langkah selesai.\n\n"
            f"PLAN:\n{plan_text}")
