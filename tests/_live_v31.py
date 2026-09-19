import sys
sys.path.insert(0, '.')
from core import client as cm, config, soul, experience, orchestra
config.ACTIVE_PROVIDER = "hy3"
cl = cm.LClient.for_provider("hy3")

def mk(goal):
    t = orchestra.Task(goal, client=cl, model="hy3")
    t.messages = [{"role": "system", "content": soul.build_system_prompt()}]
    return t

print("=== TASK 1 (multi-subtask, graph+deps) ===")
t1 = mk("Buat project kecil di workspace/v31_demo: file greeting.py berisi fungsi "
        "halo(nama) yang return string 'Halo {nama}!', lalu file test_greeting.py yang "
        "test fungsi itu dengan assert, jalankan test-nya dengan python3, dan verifikasi "
        "keluaran test PASS.")
orchestra.run(t1)
print(orchestra.report_text(t1))

print("\n=== TASK 2 (serupa — harus recall task 1) ===")
t2 = mk("Buat project kecil di workspace/v31_demo2: file farewell.py berisi fungsi "
        "dadah(nama) return string 'Dadah {nama}!', plus file test_farewell.py dengan "
        "assert, jalankan test-nya dan verifikasi PASS.")
orchestra.run(t2)
print(orchestra.report_text(t2))

print("\n=== EVIDENCE ===")
h = experience.all_tasks()
e1 = [x for x in h if x.get("id") == t1.id]
e2 = [x for x in h if x.get("id") == t2.id]
print("task1 result:", e1[0]["result"] if e1 else "?", "| subtasks:", e1[0]["subtasks"] if e1 else "?")
print("task2 memory_used:", e2[0]["memory_used_ids"] if e2 else "?")
print("task2 approach (dari planner):", e2[0]["approach"] if e2 else "?")
print("metrics:", experience.metrics())
