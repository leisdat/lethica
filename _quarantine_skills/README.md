# Skill Quarantine — kurasi 2026-09-28

Skill-skill di folder ini **dipindah keluar dari `skills/`** sehingga tidak lagi
terindex/di-load oleh Lethica. Struktur subfolder dipertahankan sama seperti
asalnya di `skills/` (mis. `_quarantine_skills/security/godmode` ← `skills/security/godmode`).

Untuk mengembalikan satu skill: `mv _quarantine_skills/<path> skills/<path>`.

## Yang dikarantina (19 skill)

**Jailbreak / bypass tooling (6):**
- `security/godmode` — auto_jailbreak.py, godmode_race.py, parseltongue.py, jailbreak-templates
- `security/jailbreak-persistence`
- `security/captcha-bypass`
- `bypass-modes`
- `bypassing-authentication-with-forced-browsing`
- `software-development/agent-prompt-tuning` — load `auto_jailbreak.py` via `exec()` + live refusal-testing ke router lokal

**Panduan exploit ofensif step-by-step (12):**
- `exploiting-active-directory-with-bloodhound`
- `exploiting-ms17-010-eternalblue-vulnerability`
- `exploiting-oauth-misconfiguration`
- `exploiting-sql-injection-with-sqlmap`
- `exploiting-vulnerabilities-with-metasploit-framework`
- `exploiting-zerologon-vulnerability-cve-2020-1472`
- `performing-binary-exploitation-analysis`
- `performing-graphql-introspection-attack`
- `performing-jwt-none-algorithm-attack`
- `performing-kerberoasting-attack`
- `performing-ssrf-vulnerability-exploitation`
- `performing-mobile-app-certificate-pinning-bypass`

**Lainnya (1):**
- `game-hacking-collection` — cheat/hack game

## Yang SENGAJA dipertahankan (defensif / dual-use legitim)

- `analyzing-*-malware`, `deobfuscating-*`, `performing-malware-triage-with-yara`,
  `reverse-engineering-malware-*` — analisis malware defensif (DFIR)
- `security/auth-security`, `security-audit`, `conducting-api-security-testing` —
  hardening & testing sistem sendiri
- `mlops/llm-refusal-benchmark` — benchmark refusal model (AI safety eval)
- `security/phishing-awareness-sim` — training awareness (referensi godmode dihapus)
- `security/frida-injector`, `analyzing-ios-app-security-with-objection` — tool RE
  general-purpose (setara ghidra)

## Catatan audit

- Total sebelum kurasi: 714 SKILL.md → sesudah: 695
- 65 skill stub (<400 char, checklist tipis) dibiarkan — tidak berbahaya, di-load on-demand
- 23 grup judul ganda menyebabkan pesan "Ambigu" di tool `skill` — dibiarkan
  (rename berisiko merusak referensi antar-skill; tool sudah menangani via disambiguasi)
