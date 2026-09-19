import sys
sys.path.insert(0, '.')
from core import client as cm, config, soul, orchestra, experience
config.ACTIVE_PROVIDER = "hy3"
cl = cm.LClient.for_provider("hy3")

GOAL = ("Buat project kecil di workspace/v32_live dengan 3 bagian INDEPENDEN yang "
        "boleh dikerjakan paralel: (1) tulis README.md berisi dokumentasi fungsi "
        "kalkulator, (2) tulis util calc.py dengan fungsi tambah(a,b) dan kali(a,b), "
        "(3) TIDAK menulis kode apa pun — hanya riset cepat apa itu 'assert' python "
        "lewat web_search lalu simpan 1 kalimat kesimpulan ke riset_assert.txt. "
        "Setelah ketiganya selesai, tahap integrasi: tulis test_calc.py yang "
        "meng-import calc dan assert tambah(2,3)==5 dan kali(2,3)==6, lalu jalankan "
        "python3 test_calc.py dan verifikasi exit 0.")

t = orchestra.Task(GOAL, client=cl, model="hy3")
t.messages = [{"role": "system", "content": soul.build_system_prompt()}]
orchestra.run(t)
print("\n==== REPORT ====")
print(orchestra.report_text(t))
print("parallel_stats:", t.parallel_stats)
print("merged artifacts:", (t.merged or {}).get("artifacts"))
print("agent_calls:", getattr(t, "agent_calls", "?"))
