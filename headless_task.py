#!/usr/bin/env python3
"""Headless driver: panggil satu task ke Lethica agent loop tanpa TUI.

Pakai config yang sama, skill index yang sama, sandbox yang sama.
Output: file di workspace + log ke stdout.

Usage: python3 ~/lethica/headless_task.py "<goal>" [--skill <layer/skill> ...] [--out <dir>]
"""
import os
import sys
import time
import json
import traceback

LETHICA_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LETHICA_DIR)
os.chdir(LETHICA_DIR)

from core import config, client as client_mod, ui, loop, tools, tags, soul  # noqa: E402

# inject console (beberapa modul print via ui.console)
client_mod.console = ui.console
tools.console = ui.console
# v3.7: dispatch native FC butuh SELF_PATH (agent_path) — driver = agent entry point
config.SELF_PATH = os.path.join(LETHICA_DIR, "headless_task.py")


def run(goal, skills=None, out=None, max_rounds=None):
    out = out or os.path.join(config.WORKSPACE, "headless-out")
    os.makedirs(out, exist_ok=True)

    # 1. system prompt (persona+memory+skills+plan+rules) — sama dengan TUI
    sysp = soul.build_system_prompt()
    print(f"[driver] system prompt: {len(sysp)} chars")

    # 2. preload skill yg diminta langsung ke system prompt tail
    extra = []
    tools._build_skill_index()
    for s in (skills or []):
        body = tools_mem_skill_show(s)
        if body.startswith("=== SKILL"):
            extra.append(body)
            print(f"[driver] skill loaded: {s} ({len(body)} chars)")
        else:
            print(f"[driver] !! skill {s}: {body[:100]}")

    # 3. client + model aktif
    cl = client_mod.LClient()
    model = config.DEFAULT_MODEL
    print(f"[driver] client base={config.DEFAULT_BASE} model={model}")

    messages = [
        {"role": "system", "content": sysp + ("\n\n" + "\n\n".join(extra) if extra else "")},
        {"role": "user", "content": goal},
    ]

    t0 = time.time()
    print(f"[driver] goal: {goal[:120]}")
    print("[driver] --- agent turn start ---")
    try:
        loop.run_agent_turn(messages, model, max_rounds=max_rounds, client=cl)
    except Exception:
        traceback.print_exc()

    dur = time.time() - t0
    print(f"[driver] --- done in {dur:.1f}s ---")

    # 4. dump percakapan akhir
    conv = os.path.join(out, "conversation.json")
    with open(conv, "w") as f:
        json.dump({"goal": goal, "model": model, "duration_s": dur,
                   "messages": messages}, f, indent=2, default=str)
    print(f"[driver] conversation: {conv}")
    return conv


def tools_mem_skill_show(name):
    from core import tools_mem
    return tools_mem.tool_skill(name, action="show")


if __name__ == "__main__":
    goal = None
    skills = []
    out = None
    rounds = None
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--skill" and i + 1 < len(args):
            skills.append(args[i + 1]); i += 2
        elif a == "--out" and i + 1 < len(args):
            out = args[i + 1]; i += 2
        elif a == "--rounds" and i + 1 < len(args):
            rounds = int(args[i + 1]); i += 2
        else:
            goal = a; i += 1
    if not goal:
        print("usage: headless_task.py <goal> [--skill layer/skill ...] [--out dir]")
        sys.exit(2)
    run(goal, skills=skills, out=out, max_rounds=rounds)
