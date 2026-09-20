#!/usr/bin/env python3
"""v2.9.5 E2E #2: markup rusak total → retry 3x → finalisasi paksa (tidak stop diam)."""
import os
import sys

HOME = os.path.expanduser("~")
sys.path.insert(0, os.path.join(HOME, "lethica"))
os.chdir(os.path.join(HOME, "lethica"))

from core import loop, tokens  # noqa: E402

BROKEN = '<tool_calls:deadbeef>\n<tool_call:deadbeef>???">\n</invoke>'
FINAL = "Tidak bisa memakai tool karena format rusak. Ini ringkasan tanpa tool."


class FakeClient:
    def __init__(self):
        self.calls = 0
        self.last_finish_reason = "stop"
        self.last_usage = {"completion_tokens": 40, "total_tokens": 400}
        self.retry_prompts = 0

    def chat_failover(self, model, messages, chain, timeout=None, stream_cb=None, tools=None):
        self.calls += 1
        joined = "\n".join(m.get("content") or "" for m in messages)
        if "format canonical PERSIS" in joined or "JANGAN ulangi markup" in joined:
            self.retry_prompts += 1
            if self.retry_prompts >= 4:
                return FINAL, model
        return BROKEN, model


tokens.budget_ok = lambda: (True, "")
cl = FakeClient()
messages = [{"role": "system", "content": "test"}, {"role": "user", "content": "cek sesuatu"}]
reply, used = loop.run_agent_turn(messages, "hy3", client=cl)

print("model calls        :", cl.calls)
print("retry prompts      :", cl.retry_prompts)
print("reply ada          :", bool(reply), "->", repr((reply or "")[:70]))
print("loop tidak hang    :", cl.calls < 20)

ok = cl.retry_prompts >= 3 and bool(reply) and cl.calls < 20
print("\nE2E2 PASS — retry canonical 3x lalu finalisasi, tidak stop diam" if ok else "\nE2E2 FAIL")
sys.exit(0 if ok else 1)
