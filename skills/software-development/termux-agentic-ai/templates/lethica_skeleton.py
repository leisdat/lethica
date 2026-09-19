#!/data/data/com.termux/files/usr/bin/python3
# lethica_skeleton.py — minimal free-form agentic AI on Termux.
# Copy this to ~/myagent/agent.py, run `pip install rich`, then `python3 agent.py`.
# Full version with all 8 native tools, sandbox, danger confirm, self-mutation,
# persona injection, and self-heal is at ~/lethica/lethica.py.

import os, sys, re, json, subprocess, urllib.request
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm

WORKSPACE = os.path.expanduser("~/myagent/workspace")
os.makedirs(WORKSPACE, exist_ok=True)
BACKEND = "http://127.0.0.1:20130/v1"
DANGER = re.compile(r"\b(rm\s+-rf|mv\s+/|dd\s+if=|wget)\b", re.I)


def in_sandbox(p):
    return os.path.realpath(p).startswith(os.path.realpath(WORKSPACE))


def chat(messages):
    body = json.dumps({"model": "Free-All", "messages": messages, "max_tokens": 2048}).encode()
    req = urllib.request.Request(
        f"{BACKEND}/chat/completions", data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": "Bearer x"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=60).read())


def run_cmd(cmd):
    if DANGER.search(cmd):
        if not Confirm.ask(f"Dangerous: `{cmd}`. Run?", default=False):
            return "cancelled"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=120, cwd=WORKSPACE)
        out = (r.stdout + r.stderr) or "(no output)"
        return out[:4000]
    except Exception as e:
        return f"error: {e}"


console = Console()
messages = [{"role": "system", "content":
    "Kamu agent teknis. Panggil <invoke name=\"antml:computer:execute_command\">"
    f"<parameter name=\"command\">CMD</parameter></invoke> untuk eksekusi. "
    f"Sandbox write di {WORKSPACE}."}]

while True:
    u = Prompt.ask("\n➜ ")
    if u in ("exit", "quit"): break
    messages.append({"role": "user", "content": u})
    for _ in range(8):
        r = chat(messages)
        reply = r["choices"][0]["message"]["content"]
        messages.append({"role": "assistant", "content": reply})
        cmds = re.findall(
            r'<invoke\s+name="antml:computer:execute_command">\s*<parameter\s+name="command">(.*?)</parameter>\s*</invoke>',
            reply, re.S)
        if not cmds: break
        results = "\n".join(f"$ {c}\n{run_cmd(c)}" for c in cmds)
        messages.append({"role": "user",
                         "content": f"<tool_response>\n{results}\n</tool_response>"})
