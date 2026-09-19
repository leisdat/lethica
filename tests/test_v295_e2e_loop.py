#!/usr/bin/env python3
"""v2.9.5 E2E: loop harus EKSEKUSI tool dari markup asing & lanjut, bukan stop.

Simulasi model hy3 yang emit markup rusak (persis dari history.json turn-0004),
lalu lihat apakah run_agent_turn benar-benar menjalankan command + lanjut ronde.
"""
import os
import sys

HOME = os.path.expanduser("~")
sys.path.insert(0, os.path.join(HOME, "lethica"))
os.chdir(os.path.join(HOME, "lethica"))

from core import config, loop, tokens  # noqa: E402

MARKER = os.path.join(HOME, "lethica", "workspace", "tools", "_v295_e2e_marker.txt")
if os.path.exists(MARKER):
    os.remove(MARKER)

# ── fake client: ronde 1 emit markup asing, ronde 2 final ────────────
FOREIGN = (
    '<tool_calls:6124c78e>\n<tool_call:6124c78e>execute_command">\n'
    '<parameter name="command">echo E2E_TOOL_RAN > ' + MARKER + '</parameter>\n'
    '</invoke>'
)
FINAL = "Selesai: tool sudah jalan dan file marker dibuat. Tidak ada yang tersisa."


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.last_finish_reason = "stop"
        self.last_usage = {"completion_tokens": 50, "total_tokens": 500}
        self.seen_tool_response = False

    def chat_failover(self, model, messages, chain, timeout=None, stream_cb=None):
        self.calls += 1
        joined = "\n".join(m.get("content") or "" for m in messages)
        if "E2E_TOOL_RAN" in joined and "<tool_response>" in joined:
            self.seen_tool_response = True
            return FINAL, model
        return FOREIGN, model


tokens.budget_ok = lambda: (True, "")
cl = FakeClient()
messages = [{"role": "system", "content": "test"}, {"role": "user", "content": "cek versi"}]
reply, used = loop.run_agent_turn(messages, "hy3", client=cl)

ok_tool = os.path.isfile(MARKER)
ok_cont = cl.seen_tool_response and cl.calls >= 2
ok_final = reply == FINAL

print("model calls         :", cl.calls)
print("marker file dibuat  :", ok_tool)
print("tool_response fed   :", cl.seen_tool_response)
print("final reply benar   :", ok_final, "->", repr((reply or "")[:70]))
print("tool_response ada di transcript:", any("<tool_response>" in (m.get("content") or "") for m in messages))

if ok_tool and ok_cont and ok_final:
    print("\nE2E PASS — loop lanjut otomatis tanpa user chat lagi")
    if os.path.exists(MARKER):
        os.remove(MARKER)
    sys.exit(0)
print("\nE2E FAIL")
sys.exit(1)
