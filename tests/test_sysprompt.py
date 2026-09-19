#!/usr/bin/env python3
"""tests/test_sysprompt.py — verifikasi system prompt optimal (<60k chars, ada katalog layer).
Jalankan: python3 ~/lethica/tests/test_sysprompt.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core import soul, tools

def ok(cond, msg):
    print(("PASS" if cond else "FAIL") + " - " + msg)
    return cond

def main():
    tools._build_skill_index()
    sp = soul.build_system_prompt()
    fails = 0
    L = len(sp)
    fails += 0 if ok(L < 60000, f"system prompt <60k chars ({L})") else 1
    fails += 0 if ok("## SKILLS" in sp, "ada SKILLS block") else 1
    fails += 0 if ok("KATALOG LAYER" in sp, "ada ringkasan katalog layer") else 1
    fails += 0 if ok("SKILL_INDEX.md" in sp, "referensi ke SKILL_INDEX.md ada") else 1
    fails += 0 if ok("coding/coding" in sp or "coding" in sp, "autoload coding ada") else 1
    # pastikan gak ada 455 entry individual (hemat token)
    fails += 0 if ok(sp.count("### KATALOG") <= 1, "katalog tidak list 455 entry") else 1
    print(f"\n{'ALL PASS' if fails==0 else str(fails)+' FAIL'} | {L} chars (~{L//4} tokens)")
    return fails

if __name__ == "__main__":
    sys.exit(1 if main() else 0)
