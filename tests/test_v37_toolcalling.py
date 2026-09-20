#!/data/data/com.termux/files/usr/bin/python3
"""tests/test_v37_toolcalling.py — v3.7 tool-calling: skema + validator + salvage
+ dispatcher native FC + jalur loop structured. Deterministic, offline (stub LLM).

CATATAN: markup tag dibangun via T() pakai [[ ]], bukan literal angle-bracket —
tool-call framing di beberapa runtime memotong payload yang mengandung markup
mirip XML tool (bug kelas yang persis lagi diuji di sini)."""
import os
import sys
import json
import tempfile

HOME = os.path.expanduser("~")
sys.path.insert(0, os.path.join(HOME, "lethica"))
os.chdir(os.path.join(HOME, "lethica"))

LQ, GQ = chr(60), chr(62)


def T(s):
    """[[tag]] -> <tag>, [[/]] -> />"""
    return s.replace("[[", LQ).replace("]]", GQ)


WS = tempfile.mkdtemp(prefix="lx-v37-",
                       dir=os.path.join(HOME, "lethica", "workspace"))
os.environ["LETHICA_MEM_DIR"] = os.path.join(WS, "memory")
os.environ["LETHICA_GRAPH_DIR"] = os.path.join(WS, "graph")

from core import config, tags, tools, tooldef  # noqa: E402

SP = config.SELF_PATH
PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("PASS " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))


# ══ 1. tooldef.validate ═══════════════════════════════════════════
c, e, w = tooldef.validate("read_file", {})
check("1a required hilang -> error", bool(e) and "path" in e[0])

c, e, w = tooldef.validate("read_file", {"path": "/x", "start": "abc"})
check("1b integer non-numerik -> error jelas", bool(e) and "integer" in e[0], str(e))

c, e, w = tooldef.validate("http_request", {"url": "http://x", "method": "post"})
check("1c enum case-insensitive -> kanonik", not e and c.get("method") == "POST", str(c))

c, e, w = tooldef.validate("list_dir", {"path": "/tmp", "recursive": "true"})
check("1d boolean coerce", not e and c.get("recursive") is True)

c, e, w = tooldef.validate("web_search", {"query": "q", "limit": "3", "extra": "x"})
check("1e unknown arg -> warning dibuang",
      not e and w and "extra" in w[0] and c == {"query": "q", "limit": 3})

c, e, w = tooldef.validate("write_file", {"path": "/x", "content": "  spaced  "})
check("1f string TIDAK di-strip", not e and c["content"] == "  spaced  ")

c, e, w = tooldef.validate("tool_tidak_ada", {})
check("1g tool asing -> error", bool(e))

c, e, w = tooldef.validate("read_file", {"PATH": "/x"})
check("1h key case-insensitive", not e and c.get("path") == "/x")

c, e, w = tooldef.validate("read_file", {"path": "/x", "start": 5})
check("1i int asli diterima", not e and c.get("start") == 5)

c, e, w = tooldef.validate("http_request", {"url": "u", "method": 5})
check("1j enum salah tipe -> error", bool(e))

# ══ 2. openai_tools schema shape ═══════════════════════════════════
tl = tooldef.openai_tools()
ok = (len(tl) == len(tooldef.TOOL_DEFS)
      and all(t["type"] == "function" and "required" in t["function"]["parameters"]
              and t["function"]["name"] in tooldef.TOOL_DEFS for t in tl))
check("2a semua tool -> schema valid OpenAI", ok, f"{len(tl)} tools")
exec_t = next(t for t in tl if t["function"]["name"] == "exec")
check("2b exec required command", exec_t["function"]["parameters"]["required"] == ["command"])

# ══ 3. canon_tool aliases ══════════════════════════════════════════
check("3a execute_command->exec", tooldef.canon_tool("execute_command") == "exec")
check("3b antml prefix->exec", tooldef.canon_tool("antml:computer:execute_command") == "exec")
check("3c Bash->exec", tooldef.canon_tool("Bash") == "exec")
check("3d grep->search_content", tooldef.canon_tool("grep") == "search_content")
check("3e unknown->None", tooldef.canon_tool("quantum_teleport") is None)

# ══ 4. salvage stage: silent-fail -> error eksplisit ═══════════════
f4 = os.path.join(WS, "salvage_target.txt")
with open(f4, "w") as f:
    f.write("SALV_OK\nline2\n")

# 4a: newline di tengah attrs → salvage harus EKSEKUSI (regex lama jatuh)
r = T(f'[[read_file\n  path="{f4}"\n  start="1" end="1"\n/]]')
out = tags.dispatch(r, SP)
check("4a salvage eksekusi tag ber-newline", "SALV_OK" in out, repr(out[:120]))

# 4b: arg salah tipe → TOOL_ERROR eksplisit (bukan dispatch diam)
out2 = tags.dispatch(T(f'[[read_file path="{f4}" start="satu" /]]'), SP)
check("4b salvage error eksplisit", "TOOL_ERROR" in out2 and "integer" in out2, repr(out2[:160]))

# 4c: required hilang → error
out3 = tags.dispatch(T("[[list_dir /]]"), SP)
check("4c missing required -> TOOL_ERROR", "TOOL_ERROR" in out3 and "path" in out3, repr(out3[:120]))

# 4d: write_file normal → TIDAK dobel dieksekusi (dedupe span)
f4d = os.path.join(WS, "once.txt")
out4 = tags.dispatch(T(f'[[write_file path="{f4d}">X[[/write_file]]'), SP)
check("4d stage-1 + salvage tidak dobel", out4.count("[write_file]") == 1, repr(out4[:120]))

# 4e: contoh di fenced code block → tetap kosong (regresi v2.8.10)
out5 = tags.dispatch("lihat:\n```\n" + T(f'[[read_file path="/etc/passwd" /]]') + "\n```", SP)
check("4e code block di-mask", out5 == "", repr(out5[:80]))

# 4f: write_file body-tag rusak (attrs newline) → salvage eksekusi
f4f = os.path.join(WS, "salvaged.txt")
out6 = tags.dispatch(T(f'[[write_file\n path="{f4f}"\n>HELLO_SALV[[/write_file]]'), SP)
check("4f salvage body-tag",
      os.path.isfile(f4f) and open(f4f).read() == "HELLO_SALV", repr(out6[:100]))

# 4g: looks_like_tool_attempt menangkap tag kanonik rusak (dulu silent)
check("4g attempt: tag kanonik rusak -> True",
      tags.looks_like_tool_attempt(T(f'[[read_file path="{f4}" start="xx"/]]')))
check("4h attempt: prose bersih -> False",
      not tags.looks_like_tool_attempt("halaman biasa tanpa tool"))

# ══ 5. dispatch_calls_list (native FC) ═════════════════════════════
f5 = os.path.join(WS, "native_marker.txt")
open(f5, "w").write("NATIVE_OK\n")  # pre-create: read_file jalan SEBELUM exec (EXEC_ORDER, lihat 5h)
calls = [
    {"id": "call_A", "type": "function", "function": {
        "name": "exec", "arguments": json.dumps({"command": f"echo EXEC_RAN > {f5}.exec"})}},
    {"id": "call_B", "type": "function", "function": {
        "name": "execute_command", "arguments": json.dumps({"command": "echo B_SECOND"})}},
    {"id": "call_C", "type": "function", "function": {
        "name": "read_file", "arguments": json.dumps({"path": f5})}},
]
res = tags.dispatch_calls_list(calls, SP)
ids = [i for i, _, _ in res]
labels = [l for _, l, _ in res]
texts = {}
for _, l, t in res:
    texts.setdefault(l, t)
check("5a tiga call tereksekusi", len(res) == 3 and os.path.isfile(f5 + ".exec"), str(labels))
check("5b semua id asli hadir", sorted(ids) == ["call_A", "call_B", "call_C"], str(ids))
check("5c alias nama di-canon", labels.count("exec") == 2)
check("5d read_file baca file", "NATIVE_OK" in texts.get("read_file", ""),
      repr(texts.get("read_file", ""))[:100])
check("5d2 exec benar-benar jalan", "EXEC_RAN" in open(f5 + ".exec").read())

bad = [
    {"id": "x1", "function": {"name": "read_file", "arguments": json.dumps({"start": 1})}},
    {"id": "x2", "function": {"name": "quantum_tool", "arguments": "{}"}},
    {"id": "x3", "function": {"name": "exec", "arguments": "bukan-json{{"}},
]
res_bad = tags.dispatch_calls_list(bad, SP)
allt = "\n".join(t for _, _, t in res_bad)
check("5e invalid -> TOOL_ERROR eksplisit x3", allt.count("TOOL_ERROR") == 3, repr(allt)[:160])
check("5f pesan sebut sebabnya",
      "hilang" in allt and "tidak dikenal" in allt and "JSON" in allt)

check("5g call list kosong -> []", tags.dispatch_calls_list([], SP) == [])

calls_order = [
    {"id": "1", "function": {"name": "exec", "arguments": json.dumps({"command": "echo O_EXEC"})}},
    {"id": "2", "function": {"name": "list_dir", "arguments": json.dumps({"path": WS})}},
]
res_o = tags.dispatch_calls_list(calls_order, SP)
check("5h urutan = EXEC_ORDER (list_dir sebelum exec)",
      [l for _, l, _ in res_o] == ["list_dir", "exec"], str([l for _, l, _ in res_o]))

# argumen dict (bukan string JSON) diterima
res_dc = tags.dispatch_calls_list(
    [{"id": "d1", "function": {"name": "list_dir", "arguments": {"path": WS}}}], SP)
check("5i arguments sebagai dict diterima", len(res_dc) == 1 and "TOOL_ERROR" not in res_dc[0][2])

# ══ 6. loop e2e: native FC path ════════════════════════════════════
from core import loop as loop_mod, tokens as tokens_mod  # noqa: E402

f6 = os.path.join(WS, "loop_marker.txt")
FINAL6 = "Selesai via native FC."


class NativeFakeClient:
    def __init__(self):
        self.calls = 0
        self.last_finish_reason = "tool_calls"
        self.last_usage = None
        self.last_tool_calls = None
        self.tools_rejected = False
        self.seen_tool_msg = False
        self.seen_tools_payload = "UNSET"

    def chat_failover(self, model, messages, chain=None, timeout=None, stream_cb=None,
                      tools=None):
        self.calls += 1
        self.seen_tools_payload = tools
        if any(m.get("role") == "tool" for m in messages):
            self.seen_tool_msg = True
            self.last_tool_calls = None
            return FINAL6, model
        self.last_tool_calls = [{
            "id": "t1", "type": "function",
            "function": {"name": "exec",
                         "arguments": json.dumps({"command": f"echo LOOP_NATIVE > {f6}"})}}]
        return "(empty reply)", model


tokens_mod.budget_ok = lambda: (True, "")
cl6 = NativeFakeClient()
msgs6 = [{"role": "system", "content": "test"}, {"role": "user", "content": "buat marker"}]
_old_stream = loop_mod.config.STREAM
loop_mod.config.STREAM = False
try:
    reply6, _ = loop_mod.run_agent_turn(msgs6, "stub", client=cl6)
finally:
    loop_mod.config.STREAM = _old_stream
tool_msgs = [m for m in msgs6 if m.get("role") == "tool"]
amsgs = [m for m in msgs6 if m.get("role") == "assistant" and m.get("tool_calls")]
check("6a tools payload dikirim ke API",
      isinstance(cl6.seen_tools_payload, list)
      and len(cl6.seen_tools_payload) == len(tooldef.TOOL_DEFS))
check("6b marker dieksekusi",
      os.path.isfile(f6) and "LOOP_NATIVE" in open(f6).read())
check("6c assistant msg ada tool_calls + id",
      bool(amsgs) and amsgs[0]["tool_calls"][0]["id"] == "t1")
check("6d empty reply tidak jadi key content",
      bool(amsgs) and "content" not in amsgs[0], repr(amsgs[:1])[:140])
check("6e role tool + tool_call_id sesuai",
      len(tool_msgs) == 1 and tool_msgs[0]["tool_call_id"] == "t1"
      and "LOOP_NATIVE" in tool_msgs[0]["content"], repr(tool_msgs[:1])[:140])
check("6f final reply bersih", reply6 == FINAL6, repr(reply6))

# 6g: NATIVE_FC=False -> payload tools tidak dikirim
cl6b = NativeFakeClient()
_old_fc = loop_mod.config.NATIVE_FC
loop_mod.config.NATIVE_FC = False
try:
    loop_mod.run_agent_turn([{"role": "system", "content": "t"},
                             {"role": "user", "content": "u"}], "stub", client=cl6b)
    check("6g NATIVE_FC=false -> tools=None", cl6b.seen_tools_payload is None)
finally:
    loop_mod.config.NATIVE_FC = _old_fc

# 6h: tools_rejected -> payload di-drop untuk turn berikutnya
cl6c = NativeFakeClient()
cl6c.tools_rejected = True
_old_stream2 = loop_mod.config.STREAM
loop_mod.config.STREAM = False
try:
    loop_mod.run_agent_turn([{"role": "system", "content": "t"},
                             {"role": "user", "content": "u"}], "stub", client=cl6c)
    check("6h tools_rejected -> payload None", cl6c.seen_tools_payload is None)
finally:
    loop_mod.config.STREAM = _old_stream2

# ══ 7. chat(): provider response tool_calls → last_tool_calls ═══════
from core import client as client_mod  # noqa: E402


class CapClient(client_mod.LClient):
    def _req(self, method, path, body=None):
        self.captured = body
        return {"choices": [{"finish_reason": "tool_calls",
                             "message": {"content": None, "tool_calls": [
                                 {"id": "z", "function":
                                  {"name": "exec",
                                   "arguments": json.dumps({"command": "x"})}}]}}],
                "usage": {}}


c7 = CapClient(base="http://x/v1", key="k")
c7.chat("m", [{"role": "user", "content": "u"}], tools=tooldef.openai_tools())
check("7a body.tools terkirim + tool_choice auto",
      "tools" in c7.captured and c7.captured.get("tool_choice") == "auto")
check("7b response tool_calls tertangkap",
      bool(c7.last_tool_calls) and c7.last_tool_calls[0]["id"] == "z")
check("7c finish_reason tool_calls", c7.last_finish_reason == "tool_calls")

c7b = CapClient(base="http://x/v1", key="k")
c7b.chat("m", [{"role": "user", "content": "u"}], tools=None)
check("7d tanpa tools -> body bersih", "tools" not in c7b.captured)

c7c = CapClient(base="http://x/v1", key="k")
c7c.chat_failover("m", [{"role": "user", "content": "u"}],
                  models_chain=["m"], tools=tooldef.openai_tools())
check("7e failover meneruskan last_tool_calls",
      bool(c7c.last_tool_calls) and c7c.last_tool_calls[0]["id"] == "z")

# ══ 8. regresi: markup asing lama tetap jalan ══════════════════════
LEGACY = (LQ + "tool_calls:x" + GQ + "\n"
          + LQ + "tool_call:x" + GQ + 'execute_command">' + "\n"
          + LQ + 'parameter name="command">echo LEGACY_OK' + LQ + "/parameter" + GQ + "\n"
          + LQ + "/invoke" + GQ)
out8 = tags.dispatch(LEGACY, SP)
check("8a legacy foreign markup jalan", "LEGACY_OK" in out8, repr(out8[:120]))
lt = tags.strip_tags(out8)
check("8b strip_tags legacy bersih",
      "tool_call" not in lt and "invoke" not in lt, repr(lt[:80]))

# exec canonical penuh tetap normal
CANON = (LQ + 'invoke name="antml:computer:execute_command"' + GQ
         + LQ + 'parameter name="command">echo CANON_OK' + LQ + "/parameter" + GQ
         + LQ + "/invoke" + GQ)
out8c = tags.dispatch(CANON, SP)
check("8c canonical exec tetap jalan", "CANON_OK" in out8c, repr(out8c[:120]))

# ══ 9. edit_file stage-1 + salvage longgar ═════════════════════════
f9 = os.path.join(WS, "ed9.txt")
open(f9, "w").write("AAA\n")
out9 = tags.dispatch(T(f'[[edit_file path="{f9}">]]<target>AAA</target>'
                       f'<replacement>BBB</replacement>[[/edit_file]]'), SP)
check("9a edit stage-1", "BBB" in open(f9).read() and out9.count("[edit_file]") == 1,
      repr(out9[:100]))

f9b = os.path.join(WS, "ed9b.txt")
open(f9b, "w").write("CCC\n")
out9b = tags.dispatch(T(f'[[edit_file  path="{f9b}" >]]\n<target>CCC</target>\n'
                        f'<replacement>DDD</replacement>\n[[/edit_file]]'), SP)
check("9b edit salvage attrs longgar",
      "DDD" in open(f9b).read() and out9b.count("[edit_file]") == 1, repr(out9b[:120]))

# ══ 10. tidak ada dobel-eksekusi pada reply campuran ═══════════════
f10 = os.path.join(WS, "mix.txt")
mixed = (T(f'[[write_file path="{f10}">A[[/write_file]]') + "\n"
         + T(f'[[write_file\n path="{f10}.salv">B[[/write_file]]'))
out10 = tags.dispatch(mixed, SP)
check("10a dua write_file jalan sekali-kali",
      open(f10).read() == "A" and open(f10 + ".salv").read() == "B"
      and out10.count("wrote to") == 2, repr(out10)[:160])

# ══ SUMMARY ═════════════════════════════════════════════════════════
print(f"\nRESULT: {len(PASS)} passed, {len(FAIL)} failed")
if FAIL:
    print("FAILED:", ", ".join(FAIL))
    sys.exit(1)
