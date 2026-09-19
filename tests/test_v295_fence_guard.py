#!/usr/bin/env python3
"""v2.9.5 guard: markup asing di code block TIDAK boleh jadi tag nyata (jaga v2.8.10)."""
import os
import sys

HOME = os.path.expanduser("~")
sys.path.insert(0, os.path.join(HOME, "lethica"))
os.chdir(os.path.join(HOME, "lethica"))
from core import tags, tools  # noqa: E402

SP = tools.config.SELF_PATH
PASS, FAIL = [], []


def check(n, c, extra=""):
    (PASS if c else FAIL).append(n)
    print(("PASS " if c else "FAIL ") + n + (f"  {extra}" if extra else ""))


# 1) markup asing contoh di fenced block → tidak dieksekusi
fenced = ('Contoh format:\n```\n<tool_calls:x>\n<tool_call:x>execute_command">\n'
          '<parameter name="command">echo NOPE</parameter>\n</invoke>\n```\nsudah')
o1 = tags.dispatch(fenced, SP)
check("fenced foreign tidak jalan", "NOPE" not in o1 and o1 == "", repr(o1[:80]))

# 2) markup asing contoh di inline backtick → tidak dieksekusi
inl = 'Pakai `<tool_calls:x><tool_call:x>execute_command">` ya.'
o2 = tags.dispatch(inl, SP)
check("inline foreign tidak jalan", o2 == "", repr(o2[:80]))

# 3) markup asing NYATA (di luar code) → tetap jalan (fix utama)
real = ('<tool_calls:6124c78e>\n<tool_call:6124c78e>execute_command">\n'
        '<parameter name="command">echo REAL_RAN</parameter>\n</invoke>')
o3 = tags.dispatch(real, SP)
check("foreign nyata tetap jalan", "REAL_RAN" in o3, repr(o3[:100]))

# 4) canonical nyata tetap jalan
o4 = tags.dispatch('<invoke name="antml:computer:execute_command"><parameter name="command">echo CANON_OK</parameter></invoke>', SP)
check("canonical tetap jalan", "CANON_OK" in o4)

# 5) canonical CONTOH di code block tetap tidak jalan
o5 = tags.dispatch('```\n<invoke name="antml:computer:execute_command"><parameter name="command">echo NO_CANON</parameter></invoke>\n```', SP)
check("canonical contoh tidak jalan", o5 == "", repr(o5[:60]))

print("\n==== %d PASS / %d FAIL ====" % (len(PASS), len(FAIL)))
sys.exit(1 if FAIL else 0)
