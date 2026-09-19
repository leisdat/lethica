#!/usr/bin/env python3
"""v2.9.5 LIVE test: turn nyata lewat routerku, tool harus jalan & loop lanjut sendiri."""
import os
import sys

HOME = os.path.expanduser("~")
sys.path.insert(0, os.path.join(HOME, "lethica"))
os.chdir(os.path.join(HOME, "lethica"))

from core import config, loop, soul  # noqa: E402
from core.client import LClient  # noqa: E402

p = config.get_provider(config.ACTIVE_PROVIDER)
cl = LClient(base=p["base"], key=p["key"])
messages = [{"role": "system", "content": soul.build_system_prompt()}]
messages.append({"role": "user", "content":
                 "Cek versi lethica sekarang: baca file .lethica_version di repo, lalu sebutkan "
                 "isinya. Satu tool call saja, lalu finalkan."})

print("provider:", config.ACTIVE_PROVIDER, "| model:", config.DEFAULT_MODEL)
reply, used = loop.run_agent_turn(messages, config.DEFAULT_MODEL, client=cl)

tr = [m for m in messages if m.get("role") == "user" and "<tool_response>" in (m.get("content") or "")]
print("\n=== HASIL ===")
print("tool_response rounds:", len(tr))
print("model terpakai     :", used)
print("final reply        :", repr((reply or "")[:300]))
print("tool benar dipanggil:", bool(tr))
if tr:
    print("tool output        :", repr(tr[0]["content"][:200]))
ver = "unknown"
try:
    with open(os.path.join(HOME, "lethica", ".lethica_version")) as f:
        ver = f.read().strip().lstrip("v")
except Exception:
    pass
ok = bool(tr) and bool(reply) and ver in (reply or "")
print("\nLIVE", "PASS — loop lanjut sendiri, tool jalan, jawaban benar" if ok else "PARTIAL/FAIL",
      f"(expected ver {ver})")
