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
    # Model harus ikut provider aktif (`[server]`) — "L" cuma alias combo di routerku,
    # provider lain (mis. dahl) balas 400 Bad Request.
    model = getattr(config, "DEFAULT_MODEL", None) or "L"
    task = ("Gunakan skill coding. Buat fungsi python `is_even(n)` yang return True kalau genap. "
            "Tulis ke workspace/_t_e2e.py lalu jalankan test.")
    fp = os.path.join(config.WORKSPACE, "_t_e2e.py")
    if os.path.exists(fp):
        os.remove(fp)
    msgs = [{"role": "system", "content": SYSP}, {"role": "user", "content": task}]
    text, outs = "", []
    for rnd in range(3):
        try:
            r = cl.chat(model, msgs, max_tokens=1500, timeout=90)
        except Exception as e:
            print("FAIL - chat exception:", e); return 1
        if not isinstance(r, dict) or "choices" not in r:
            print("FAIL - respon bukan dict/chat:", str(r)[:200]); return 1
        text = r["choices"][0]["message"]["content"] or ""
        outs += tags.dispatch(text, agent_path=os.path.abspath(__file__))
        if os.path.exists(fp):
            break
        # ronde lanjutan: model cuma eksplorasi (mis. ls skills) di turn 1 → dorong aksi nyata
        msgs.append({"role": "assistant", "content": text})
        msgs.append({"role": "user",
                     "content": "Lanjutkan sekarang: tulis file lewat tag write_file, lalu jalankan test."})
    fails = 0
    fails += 0 if ok("write_file" in text or "execute_command" in text or outs, "model generate tool call") else 1
    # cek file kebikin
    if os.path.exists(fp):
        print("PASS - file tertulis:", fp)
        os.remove(fp)
    else:
        print("FAIL - file tidak tertulis")
        fails += 1
    return fails

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
