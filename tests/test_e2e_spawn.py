#!/usr/bin/env python3
"""tests/test_e2e_spawn.py — spawn Lethica sub-agent headless + task coding.
Butuh routerku jalan (sk-routerku valid). Skip otomatis kalau upstream timeout.
Jalankan: python3 ~/lethica/tests/test_e2e_spawn.py
"""
import os, sys, json, urllib.request
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import config, client, tags, soul, tools

def ok(cond, msg):
    print(("PASS" if cond else "FAIL") + " - " + msg)
    return cond

def router_alive():
    try:
        req = urllib.request.Request("http://127.0.0.1:20130/v1/models",
            headers={"Authorization": "Bearer sk-routerku"})
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception:
        return False

def main():
    if not router_alive():
        print("SKIP - routerku tidak respon (jalankan dulu)")
        return 0
    tools._build_skill_index()
    SYSP = soul.build_system_prompt()
    if len(SYSP) > 60000:
        print("FAIL - system prompt terlalu besar untuk e2e")
        return 1
    cl = client.LClient()
    task = ("Gunakan skill coding. Buat fungsi python `is_even(n)` yang return True kalau genap. "
            "Tulis ke workspace/_t_e2e.py lalu jalankan test.")
    try:
        r = cl.chat("L", [{"role":"system","content":SYSP},{"role":"user","content":task}],
                    max_tokens=1500, timeout=90)
    except Exception as e:
        print("FAIL - chat exception:", e); return 1
    if not isinstance(r, dict) or "choices" not in r:
        print("FAIL - respon bukan dict/chat:", str(r)[:200]); return 1
    text = r["choices"][0]["message"]["content"]
    outs = tags.dispatch(text, agent_path=os.path.abspath(__file__))
    fails = 0
    fails += 0 if ok("write_file" in text or "execute_command" in outs, "model generate tool call") else 1
    # cek file kebikin
    fp = os.path.join(config.WORKSPACE, "_t_e2e.py")
    if os.path.exists(fp):
        print("PASS - file tertulis:", fp)
        os.remove(fp)
    else:
        print("FAIL - file tidak tertulis")
        fails += 1
    return fails

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
