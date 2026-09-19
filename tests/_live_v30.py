import sys
sys.path.insert(0, '.')
from core import client as cm, config, orchestra
config.ACTIVE_PROVIDER = "hy3"
cl = cm.LClient.for_provider("hy3")
goal = ("Buat file workspace/hello_orchestra.txt berisi teks 'halo dari orchestrator', "
        "lalu verifikasi isinya pakai read_file.")
t = orchestra.Task(goal, client=cl, model="hy3")
from core import soul
t.messages = [{"role":"system","content":soul.build_system_prompt()}]  # prompt penuh: instruksi tool tag resmi
orchestra.run(t)
print(orchestra.report_text(t))
import os
p = os.path.join(config.WORKSPACE, "hello_orchestra.txt")
print("FILE NYATA:", repr(open(p).read()) if os.path.isfile(p) else "TIDAK ADA")
print("STATE:", t.state, "| tool_calls:", t.tool_calls)
