#!/usr/bin/env python3
"""tests/test_skills_loader.py — unit test untuk skill loader Lethica.
Jalankan: python3 ~/lethica/tests/test_skills_loader.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import tools

def ok(cond, msg):
    print(("PASS" if cond else "FAIL") + " - " + msg)
    return cond

def main():
    tools._build_skill_index()
    idx = tools._SKILL_INDEX
    alias = tools._SKILL_ALIAS
    fails = 0

    # 1. index ter-build, >400 skill
    fails += 0 if ok(len(idx) > 400, f"index ter-build ({len(idx)} skill)") else 1

    # 2. relkey format "layer/skill"
    sample = list(idx)[:5]
    fails += 0 if ok(all("/" in k for k in sample), "key pakai format layer/skill") else 1

    # 3. collision: basename ganda resolve via alias
    coll = {k: v for k, v in alias.items() if len(v) > 1}
    fails += 0 if ok(len(coll) >= 20, f"ada basename collision ({len(coll)}) -> alias jalan") else 1

    # 4. container layer: 'security' gak ada sbg relkey tapi ada sub-skill
    fails += 0 if ok("security" not in idx and any(k.startswith("security/") for k in idx),
                     "layer container 'security' -> sub-skill list") else 1

    # 5. tool_skill exact (entry-point layer 'coding' -> relkey 'coding')
    r = tools.tool_skill("coding", "show")
    fails += 0 if ok(r.startswith("=== SKILL: coding ==="), "tool_skill exact relkey (entry-point)") else 1

    # 5b. exact sub-skill (coding-core adalah entry-point layer -> relkey 'coding-core')
    r = tools.tool_skill("coding-core", "show")
    fails += 0 if ok(r.startswith("=== SKILL: coding-core ==="), "tool_skill exact sub-skill (entry-point)") else 1

    # 6. tool_skill ambigu -> list kandidat
    r = tools.tool_skill("database", "show")
    fails += 0 if ok("Ambigu" in r, "tool_skill ambigu kasih daftar") else 1

    # 7. tool_skill container -> daftar sub-skill
    r = tools.tool_skill("security", "show")
    fails += 0 if ok("container" in r and "security/security-core" in r, "tool_skill container list") else 1

    # 8. tool_skill not-found
    r = tools.tool_skill("zzz-nope", "show")
    fails += 0 if ok("gak ketemu" in r, "tool_skill not-found pesan jelas") else 1

    # 9. list action -> section per layer
    r = tools.tool_skill(action="list")
    fails += 0 if ok(r.count("### ") > 30, f"list punya section per-layer ({r.count('### ')})") else 1

    # 10. file sub-load (entry-point 'coding' gak punya references/nonexist.md)
    r = tools.tool_skill("coding", "show", file="nonexist.md")
    fails += 0 if ok("gak ada" in r, "tool_skill file tidak ada -> pesan") else 1

    print(f"\n{'ALL PASS' if fails==0 else str(fails)+' FAIL'}")
    return fails

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
