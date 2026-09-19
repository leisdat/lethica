#!/usr/bin/env python3
"""v2.9.5 regression: normalizer tool-call format asing + safety-net."""
import os
import sys

sys.path.insert(0, os.path.expanduser("~/lethica"))
from core import tags, tools  # noqa: E402

SP = tools.config.SELF_PATH
PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


def norm(s):
    return tags.sanitize_tool_tags(s)


# ── CASE 1: markup asing persis dari history.json turn terakhir ──────
c1 = ('<tool_calls:6124c78e>\n<tool_call:6124c78e>execute_command">\n'
      '<parameter name="command">echo C1_OK</parameter>\n</invoke>')
n1 = norm(c1)
check("c1 EXEC_TAG_RE match", bool(tools.EXEC_TAG_RE.search(n1)), repr(n1[:120]))
out1 = tags.dispatch(c1, SP)
check("c1 dispatch jalan", "C1_OK" in out1, repr(out1[:160]))
check("c1 strip_tags bersih", "tool_call" not in tags.strip_tags(c1),
      repr(tags.strip_tags(c1)))

# ── CASE 2: <invoke name="execute_command"> tanpa prefix antml ───────
c2 = '<invoke name="execute_command"><parameter name="command">echo C2_OK</parameter></invoke>'
out2 = tags.dispatch(c2, SP)
check("c2 dispatch jalan", "C2_OK" in out2, repr(out2[:160]))

# ── CASE 3: function_calls + read_file ───────────────────────────────
c3 = ('<function_calls>\n<invoke name="read_file">\n'
      '<parameter name="path">~/lethica/.lethica_version</parameter>\n'
      '</invoke>\n</function_calls>')
out3 = tags.dispatch(c3, SP)
check("c3 read_file jalan", "v2.9" in out3, repr(out3[:160]))
check("c3 tanpa sisa wrapper", "function_calls" not in tags.strip_tags(c3))

# ── CASE 4: alias nama tool (Bash / Read / Grep) ─────────────────────
c4 = '<invoke name="Bash"><parameter name="cmd">echo C4_OK</parameter></invoke>'
out4 = tags.dispatch(c4, SP)
check("c4 alias Bash→exec", "C4_OK" in out4, repr(out4[:120]))

c4b = '<invoke name="Grep"><parameter name="pattern">VERSION</parameter><parameter name="path">/data/data/com.termux/files/home/lethica/core</parameter></invoke>'
out4b = tags.dispatch(c4b, SP)
check("c4b alias Grep→search_content", "config.py" in out4b or "VERSION" in out4b, repr(out4b[:140]))

# ── CASE 5: canonical lama TIDAK regresi ─────────────────────────────
c5 = '<invoke name="antml:computer:execute_command"><parameter name="command">echo C5_OK</parameter></invoke>'
out5 = tags.dispatch(c5, SP)
check("c5 canonical tetap jalan", "C5_OK" in out5, repr(out5[:120]))
check("c5 canonical tidak diubah", 'name="antml:computer:execute_command"' in norm(c5))

# ── CASE 6: tag di dalam code block TIDAK dieksekusi (v2.8.10) ───────
c6 = 'Contoh pemakaian:\n```\n<invoke name="antml:computer:execute_command"><parameter name="command">echo SHOULD_NOT_RUN</parameter></invoke>\n```\nselesai'
check("c6 code block di-mask", tags.dispatch(c6, SP) == "",
      repr(tags.dispatch(c6, SP)[:80]))

# ── CASE 7: prose biasa TIDAK dianggap tool attempt ──────────────────
c7 = "Ini jawaban biasa tanpa tool. Selesai."
check("c7 prose biasa false", tags.looks_like_tool_attempt(c7) is False)

# ── CASE 8: safety-net mendeteksi markup rusak ───────────────────────
check("c8 deteksi markup asing", tags.looks_like_tool_attempt(c1) is True)
check("c8 deteksi invoke rusak", tags.looks_like_tool_attempt(
    '<tool_calls:abc>\n<tool_call:abc>read_file">\n</invoke>') is True)
check("c8 prose 'invoke the function' false",
      tags.looks_like_tool_attempt("Kita harus invoke the function sekarang.") is False)

# ── CASE 9: write_file foreign → canonical, path & konten utuh ───────
tgt = os.path.expanduser("~/lethica/workspace/tools/_v295_wtest.txt")
c9 = ('<invoke name="write_file"><parameter name="path">' + tgt +
      '</parameter><parameter name="content">V295_CONTENT</parameter></invoke>')
out9 = tags.dispatch(c9, SP)
ok9 = os.path.isfile(tgt) and open(tgt).read() == "V295_CONTENT"
check("c9 write_file foreign jalan", ok9, repr(out9[:120]))
if os.path.isfile(tgt):
    os.remove(tgt)

# ── CASE 10: nilai atribut mengandung kutip gak bikin tag rusak ──────
c10 = ('<invoke name="write_file"><parameter name="path">' + tgt +
       '</parameter><parameter name="content">he said "hi" ok</parameter></invoke>')
tags.dispatch(c10, SP)
ok10 = os.path.isfile(tgt) and open(tgt).read() == 'he said "hi" ok'
check("c10 quote di value aman", ok10,
      repr(open(tgt).read() if os.path.isfile(tgt) else "NO FILE"))
if os.path.isfile(tgt):
    os.remove(tgt)

print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
if FAIL:
    print("FAILED:", FAIL)
    sys.exit(1)
print("ALL v2.9.5 CHECKS PASSED")
