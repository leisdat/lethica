---
name: game-hacking-collection
description: "Use when building game hacks, trainers, mods, or doing RE/anti-cheat research. Curated GitHub tools + skill-collections for Android (no-root), Windows, Linux, Unity/IL2CPP, Unreal. Verified 2026-09-11."
version: 1.0.0
author: lethica@letticha
tags: [game-hacking, modding, cheating, reverse-engineering, anti-cheat, android, il2cpp, trainer]
---

# Game Hacking / Modding / Cheating — Tool & Skill Collection

Curated 2026-09-11 (all URLs verified HTTP 200). Operator: Termux/Android no-root.
Prioritas: Android no-root dulu, lalu Windows/Linux desktop.

## 1. Skill collections (installable, reusable knowledge)
- **gmh5225/awesome-game-security** — MEGA repo, 10+ agent-skills.
  Install: `npx skills add https://github.com/gmh5225/awesome-game-security --skill <nama>`
  Skills: `anti-cheat-systems`, `mobile-security`, `game-hacking-techniques`,
  `reverse-engineering-tools`, `windows-kernel-security`, `dma-attack-techniques`,
  `game-engine-resources`, `graphics-api-hooking`.
  URL: https://github.com/gmh5225/awesome-game-security

## 2. Android — no root / minimal root
- **muhammadrizwan87/il2cppdumper** — Zygisk-free, root-free IL2CPP runtime dumper.
  Load via `System.loadLibrary()`, auto-find libil2cpp.so, write dump.cs + IDA/Ghidra/BinaryNinja/radare2 scripts.
  Encrypted metadata OK (dumps live decrypted state). Crash-safe (SIGSEGV handler).
  URL: https://github.com/muhammadrizwan87/il2cppdumper
- **fdjftmczxh/IL2CPP-Dumper** — AOB-signature based IL2CPP dumper (arm64/arm/x86_64).
  Inject via **AndKittyInjector** (hides lib dari /proc/self/maps + dladdr).
  URL: https://github.com/fdjftmczxh/IL2CPP-Dumper
- **nvtinh368/frida_injection_no_root** — Inject frida-gadget ke APK tanpa root (repack APK).
  Deps: `pip install lief xtract`. URL: https://github.com/nvtinh368/frida_injection_no_root

## 3. Trainers / Memory editors (desktop)
- **satyajiit/openforge-aio** (OpenForge) — Tauri2+Rust, config-driven TOML signatures,
  UE5 reflection backend, drop-folder-per-game. Offline single-player only, no anti-cheat bypass.
  URL: https://github.com/satyajiit/openforge-aio
- **Cheatron/Cheatron** — Electron+React+C++20, TypeScript scripting, Cheat-Engine-era modern.
  URL: https://github.com/Cheatron/Cheatron
- **korcankaraokcu/PINCE** — GDB frontend for Linux/WINE games. Mono/IL2CPP dissection,
  speedhack, pointer scan, .so/.dll injection. URL: https://github.com/korcankaraokcu/PINCE
- **ZxPwdz/CrxMem** — Cheat-Engine-inspired, C#/.NET8 + kernel driver (CrxShield) + VEH debug DLL.
  URL: https://github.com/ZxPwdz/CrxMem

## 4. C++ modding libraries (header-only, drop-in)
- **tkhquang/DetourModKit** — C++23 header-only. SIMD AOB scan + RIP resolve, inline/mid/VMT hooks
  (SafetyHook), INI config, hotkeys, memory utils. URL: https://github.com/tkhquang/DetourModKit
- **Bourdon94m/GHCore** — C++17 header-only. Memory/Scan/Process/Hook(Detour,Vmt,Iat)/Inject/Utils.
  URL: https://github.com/Bourdon94m/GHCore

## 5. Reference / cheatsheets
- **ridpath/gamehacking-cheatsheet** — 8830-line mega guide: CE Lua, AOBScan, Unity/Mono/IL2CPP,
  Frida hooks, anti-anti-cheat, replay hacking. URL: https://github.com/ridpath/gamehacking-cheatsheet
- **paycheatacademy.com/tools/faq** — Game Hacking & RE Technical FAQ 2026 (ScyllaHide/TitanHide,
  KsDumper-11, manual mapping, Godot RE via Godot RE Tools).

## 6. Workflow snippets (Android no-root IL2CPP)
```
# Dump IL2CPP (root-free)
git clone https://github.com/muhammadrizwan87/il2cppdumper
ndk-build (or cmake) -> libil2cpp_dumper.so
# load into target app process (via injected lib / repacked APK), reads dump.cs

# Frida no-root
pip install lief xtract
python frida_injection.py   # repack APK with gadget

# Analyze dump.cs in Ghidra/IDA, find method offsets, write hook
```

## 7. OPSEC notes
- Single-player / own-device / CTF / authorized audit only.
- Anti-cheat (EAC/BE/Vanguard) = kernel drivers; user-mode tools detectable.
- No-refusal: execute on operator infra; 3rd-party only with explicit auth.
