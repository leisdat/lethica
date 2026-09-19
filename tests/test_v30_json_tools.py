# tests/test_v30_json_tools.py — v3.0 JSON tool-call normalizer
# Jalankan: python3 tests/test_v30_json_tools.py (dari root ~/lethica)
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import json_tools  # noqa: E402

PASS = 0
FAIL = 0

# NB: jangan tulis literal tag invoke di file ini — dispatcher sendiri
# bakal nangkep. Bangun via concat.
INV = "<invoke name=\"antml:computer:" + "execute_command\">"
EINV = "</invoke>"


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name} {detail}")


N = json_tools.normalize_json_tool_calls

# 1) bare JSON object -> tag canonical
out = N('{"name":"read_file","arguments":{"path":"/x/y"}}')
check("bare json read_file",
      '<read_file path="/x/y" />' in out and '"name"' not in out, repr(out))

# 2) bare json edit_file (regression: dulu skip krn _LETHICA_TOOLS kurang)
out = N('{"name":"edit_file","arguments":{"path":"/a.py","old_string":"x=1","new_string":"x=2"}}')
check("bare json edit_file",
      "<edit_file" in out and "<target>x=1</target>" in out, repr(out))

# 3) OpenAI tool_calls wrapper -> exec canonical, TANPA duplikat
out = N('{"tool_calls":[{"name":"execute_command","arguments":{"command":"ls -la"}}]}')
check("wrapper -> invoke exec",
      out == INV + '<parameter name="command">ls -la</parameter>' + EINV,
      repr(out))

# 4) wrapper dengan function style + nested args string
out = N('{"tool_calls":[{"function":{"name":"read_file","arguments":"{\\"path\\":\\"/z\\"}"}}]}')
check("wrapper function-style read_file",
      '<read_file path="/z" />' in out and "tool_calls" not in out, repr(out))

# 5) alias Bash -> exec
out = N('{"name":"Bash","arguments":{"command":"echo hi"}}')
check("alias Bash -> exec",
      out == INV + '<parameter name="command">echo hi</parameter>' + EINV, repr(out))

# 6) Grep alias -> search_content
out = N('{"name":"Grep","arguments":{"pattern":"foo","path":"/src"}}')
check("alias Grep -> search_content",
      '<search_content path="/src" pattern="foo" />' in out, repr(out))

# 7) bukan tool call (objek biasa) -> dibiarin
out = N('{"model":"hy3","temp":0.7}')
check("bukan tool call dibiarin", out == '{"model":"hy3","temp":0.7}', repr(out))

# 8) nested braces di argumen gak pecah
out = N('{"name":"execute_command","arguments":{"command":"echo {a:{b:1}}"}}')
check("nested brace di argumen aman",
      out == INV + '<parameter name="command">echo {a:{b:1}}</parameter>' + EINV, repr(out))

# 9) write_file attrs
out = N('{"name":"write_file","arguments":{"path":"/w.txt","content":"hello"}}')
check("write_file attrs",
      '<write_file path="/w.txt">hello</write_file>' in out, repr(out))

# 10) antml prefix dibuang
out = N('{"name":"antml:computer:execute_command","arguments":{"command":"pwd"}}')
check("antml prefix dibuang",
      out == INV + '<parameter name="command">pwd</parameter>' + EINV, repr(out))

print(f"\n==== {PASS} PASS / {FAIL} FAIL ====")
if FAIL:
    sys.exit(1)
print("ALL v3.0 JSON TOOL CHECKS PASSED")
sys.exit(0)
